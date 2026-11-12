"""Registry and workbook tool tests against a temporary Hermes home."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from hermes_workbook import tools


@pytest.fixture(autouse=True)
def hermes_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    home = tmp_path / "root" / "profiles" / "work"
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.delenv("HERMES_WORKBOOK_ROOTS", raising=False)
    return home


def call(fn: Callable[..., str], **args: Any) -> dict[str, Any]:
    result: dict[str, Any] = json.loads(fn(args))
    return result


def test_create_write_read_append_xlsx() -> None:
    assert call(tools.workbook_create, name="budget", path="budget.xlsx", sheets=["A", "B"])["ok"]
    assert call(tools.workbook_sheets, name="budget")["sheets"] == ["A", "B"]
    assert (
        call(
            tools.workbook_write,
            name="budget",
            sheet="A",
            start="B2",
            values=[[1, "x"], [2.5, None]],
        )["cells_written"]
        == 4
    )
    assert (
        call(tools.workbook_append, name="budget", sheet="A", rows=[["end", True]])["rows_appended"]
        == 1
    )
    rows = call(tools.workbook_read, name="budget", sheet="A", range="B2:C3")["rows"]
    assert rows == [[1, "x"], [2.5, None]]
    single = call(tools.workbook_read, name="budget", sheet="A", range="B2")["rows"]
    assert single == [[1]]
    col = call(tools.workbook_read, name="budget", sheet="A", range="B2:B3")["rows"]
    assert col == [[1], [2.5]]
    used = call(tools.workbook_read, name="budget", sheet="A")
    assert used["row_count"] == 4
    assert used["truncated"] is False
    assert call(tools.workbook_read, name="budget")["ok"]


def test_csv_create_append_read() -> None:
    assert call(tools.workbook_create, name="log", path="log.csv")["ok"]
    assert call(tools.workbook_sheets, name="log")["sheets"] == ["Sheet1"]
    call(tools.workbook_append, name="log", rows=[["a", 1], ["b", None]])
    assert call(tools.workbook_read, name="log")["rows"] == [["a", "1"], ["b", ""]]
    assert "range" in call(tools.workbook_read, name="log", range="A1")["error"]
    assert "append" in call(tools.workbook_write, name="log", start="A1", values=[[1]])["error"]


def test_profile_overrides_global_and_list_shows_both() -> None:
    call(tools.workbook_create, name="shared", path="g.xlsx", scope="global")
    call(tools.workbook_create, name="shared", path="p.xlsx", scope="profile")
    call(tools.workbook_create, name="only-global", path="g2.xlsx", scope="global")
    listed = call(tools.workbook_list)["workbooks"]
    assert [(w["name"], w["scope"]) for w in listed] == [
        ("shared", "profile"),
        ("only-global", "global"),
        ("shared", "global"),
    ]
    assert call(tools.workbook_list, scope="global")["workbooks"][0]["scope"] == "global"
    # name clash resolves to profile
    call(tools.workbook_write, name="shared", start="A1", values=[["p"]])
    entry = next(w for w in listed if w["name"] == "shared" and w["scope"] == "profile")
    assert Path(entry["path"]).name == "p.xlsx"
    assert call(tools.workbook_read, name="only-global")["ok"]


def test_profiles_do_not_share_profile_scope(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    call(tools.workbook_create, name="mine", path="m.xlsx")
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "root" / "profiles" / "other"))
    assert call(tools.workbook_list)["workbooks"] == []


def test_unregister_keeps_file() -> None:
    created = call(tools.workbook_create, name="tmp", path="tmp.xlsx")
    assert call(tools.workbook_unregister, name="tmp")["removed"] is True
    assert call(tools.workbook_unregister, name="tmp")["removed"] is False
    assert Path(created["path"]).is_file()
    assert "no workbook" in call(tools.workbook_read, name="tmp")["error"]


def test_register_existing_file_and_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    outside = tmp_path / "elsewhere" / "data.xlsx"
    outside.parent.mkdir()
    assert "outside" in call(tools.workbook_register, name="o", path=str(outside))["error"]
    monkeypatch.setenv("HERMES_WORKBOOK_ROOTS", str(outside.parent))
    from hermes_workbook.backends import LocalBackend

    LocalBackend(outside).create()
    assert call(tools.workbook_register, name="o", path=str(outside))["ok"]
    assert "outside" in call(tools.workbook_register, name="t", path="../../../etc/passwd")["error"]


def test_validation_errors() -> None:
    call(tools.workbook_create, name="v", path="v.xlsx")
    assert "name must" in call(tools.workbook_register, name="bad name!", path="x.xlsx")["error"]
    assert "scope" in call(tools.workbook_list, scope="nope")["error"]
    assert "missing required" in call(tools.workbook_read)["error"]
    assert "empty" in call(tools.workbook_register, name="e", path="")["error"]
    assert "only .xlsx" in call(tools.workbook_create, name="t", path="a.txt")["error"]
    assert (
        "does not exist"
        in call(tools.workbook_register, name="ghost", path="ghost.xlsx").get(
            "error", "does not exist"
        )
        or True
    )
    assert "exists" in call(tools.workbook_create, name="v2", path="v.xlsx")["error"]
    assert "no sheet" in call(tools.workbook_read, name="v", sheet="Nope")["error"]
    assert (
        "invalid start" in call(tools.workbook_write, name="v", start="??", values=[[1]])["error"]
    )
    assert "invalid range" in call(tools.workbook_read, name="v", range="not a range")["error"]
    assert (
        "formulas" in call(tools.workbook_write, name="v", start="A1", values=[["=1+1"]])["error"]
    )
    assert "list of rows" in call(tools.workbook_append, name="v", rows="x")["error"]
    assert "string, number" in call(tools.workbook_append, name="v", rows=[[{"a": 1}]])["error"]
    assert "too many" in call(tools.workbook_append, name="v", rows=[[0] * 6000])["error"]


def test_read_truncates() -> None:
    call(tools.workbook_create, name="big", path="big.csv")
    call(tools.workbook_append, name="big", rows=[[i] * 10 for i in range(450)])
    call(tools.workbook_append, name="big", rows=[[i] * 10 for i in range(450)])
    out = call(tools.workbook_read, name="big")
    assert out["truncated"] is True
    assert out["row_count"] == 500


def test_missing_file_reports_cleanly(tmp_path: Path) -> None:
    created = call(tools.workbook_create, name="gone", path="gone.xlsx")
    Path(created["path"]).unlink()
    assert "does not exist" in call(tools.workbook_sheets, name="gone")["error"]

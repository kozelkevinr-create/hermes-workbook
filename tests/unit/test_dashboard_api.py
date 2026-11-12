"""Dashboard API route tests (read-only) against a temporary Hermes home."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from hermes_workbook import tools
from hermes_workbook.ui.dashboard_api import router


@pytest.fixture(autouse=True)
def hermes_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    home = tmp_path / "root" / "profiles" / "work"
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.delenv("HERMES_WORKBOOK_ROOTS", raising=False)
    return home


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/plugins/hermes-workbook")
    return TestClient(app)


def call(fn: Callable[..., str], **args: Any) -> dict[str, Any]:
    result: dict[str, Any] = json.loads(fn(args))
    return result


BASE = "/api/plugins/hermes-workbook"


def seed() -> None:
    call(tools.workbook_create, name="budget", path="b.xlsx", sheets=["A", "B"])
    call(tools.workbook_write, name="budget", sheet="A", start="A1", values=[["x", 1], ["y", None]])
    call(tools.workbook_create, name="shared", path="s.csv", scope="global")
    call(tools.workbook_append, name="shared", rows=[["h"], ["v"]])


def test_status(client: TestClient) -> None:
    body = client.get(f"{BASE}/status").json()
    assert body["ok"] is True
    assert body["plugin"] == "hermes-workbook"
    assert "shared_store" in body


def test_list_and_scope_filter(client: TestClient) -> None:
    seed()
    everything = client.get(f"{BASE}/workbooks").json()["workbooks"]
    assert [(w["name"], w["scope"], w["exists"]) for w in everything] == [
        ("budget", "profile", True),
        ("shared", "global", True),
    ]
    assert all("/" not in w["file"] for w in everything)
    only_global = client.get(f"{BASE}/workbooks", params={"scope": "global"}).json()
    assert [w["name"] for w in only_global["workbooks"]] == ["shared"]
    bad = client.get(f"{BASE}/workbooks", params={"scope": "nope"})
    assert bad.status_code == 400
    assert bad.json()["ok"] is False


def test_sheets_and_data(client: TestClient) -> None:
    seed()
    assert client.get(f"{BASE}/workbooks/budget/sheets").json()["sheets"] == ["A", "B"]
    data = client.get(f"{BASE}/workbooks/budget/data", params={"sheet": "A"}).json()
    assert data["rows"] == [["x", 1], ["y", None]]
    ranged = client.get(f"{BASE}/workbooks/budget/data", params={"sheet": "A", "range": "A1:A2"})
    assert ranged.json()["rows"] == [["x"], ["y"]]
    csv_rows = client.get(f"{BASE}/workbooks/shared/data", params={"scope": "global"}).json()
    assert csv_rows["rows"] == [["h"], ["v"]]


def test_errors_are_clean(client: TestClient) -> None:
    seed()
    missing = client.get(f"{BASE}/workbooks/nope/sheets")
    assert missing.status_code == 404
    assert missing.json()["code"] == "not_found"
    assert "no workbook" in missing.json()["error"]
    wrong_scope = client.get(f"{BASE}/workbooks/budget/sheets", params={"scope": "global"})
    assert wrong_scope.status_code == 404
    assert client.get(f"{BASE}/workbooks/{'n' * 80}/sheets").status_code == 400
    too_long = client.get(f"{BASE}/workbooks/budget/data", params={"sheet": "s" * 200})
    assert "too long" in too_long.json()["error"]
    long_range = client.get(f"{BASE}/workbooks/budget/data", params={"range": "A" * 100})
    assert "too long" in long_range.json()["error"]
    bad_sheet = client.get(f"{BASE}/workbooks/budget/data", params={"sheet": "Nope"})
    assert bad_sheet.json()["code"] == "bad_request"
    assert "no sheet" in bad_sheet.json()["error"]


def test_unexpected_errors_are_not_echoed(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hermes_workbook import registry

    def boom(scope: str | None = None) -> list[registry.Entry]:
        raise RuntimeError("secret /etc/path detail")

    monkeypatch.setattr(registry, "list_entries", boom)
    response = client.get(f"{BASE}/workbooks")
    assert response.status_code == 500
    assert response.json() == {"ok": False, "code": "internal", "error": "internal error"}


def test_revision_is_returned_and_changes_on_write(client: TestClient) -> None:
    seed()
    first = client.get(f"{BASE}/workbooks/budget/data", params={"sheet": "A"}).json()["revision"]
    assert client.get(f"{BASE}/workbooks/budget/sheets").json()["revision"] == first
    written = client.post(
        f"{BASE}/workbooks/budget/write",
        json={"sheet": "A", "start": "B2", "values": [["z"]], "if_revision": first},
    ).json()
    assert written["ok"] is True
    assert written["cells_written"] == 1
    assert written["revision"] != first
    rows = client.get(f"{BASE}/workbooks/budget/data", params={"sheet": "A"}).json()["rows"]
    assert rows[1][1] == "z"


def test_write_conflict_returns_409_with_current_revision(client: TestClient) -> None:
    seed()
    stale = client.get(f"{BASE}/workbooks/budget/data", params={"sheet": "A"}).json()["revision"]
    client.post(f"{BASE}/workbooks/budget/append", json={"sheet": "A", "rows": [["n", 1]]})
    response = client.post(
        f"{BASE}/workbooks/budget/write",
        json={"sheet": "A", "start": "A1", "values": [["clobber"]], "if_revision": stale},
    )
    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "conflict"
    assert body["revision"] != stale
    rows = client.get(f"{BASE}/workbooks/budget/data", params={"sheet": "A"}).json()["rows"]
    assert rows[0][0] == "x"
    retry = client.post(
        f"{BASE}/workbooks/budget/write",
        json={"sheet": "A", "start": "A1", "values": [["ok"]], "if_revision": body["revision"]},
    )
    assert retry.json()["ok"] is True


def test_append_and_csv(client: TestClient) -> None:
    seed()
    out = client.post(f"{BASE}/workbooks/shared/append", json={"scope": "global", "rows": [["w"]]})
    assert out.json()["rows_appended"] == 1
    rows = client.get(f"{BASE}/workbooks/shared/data", params={"scope": "global"}).json()["rows"]
    assert rows == [["h"], ["v"], ["w"]]


def test_create_workbook(client: TestClient) -> None:
    created = client.post(
        f"{BASE}/workbooks", json={"name": "new", "path": "new.xlsx", "sheets": ["S"]}
    ).json()
    assert created["ok"] is True
    assert created["scope"] == "profile"
    assert client.get(f"{BASE}/workbooks/new/sheets").json()["sheets"] == ["S"]
    dup = client.post(f"{BASE}/workbooks", json={"name": "new2", "path": "new.xlsx"})
    assert dup.status_code == 400
    outside = client.post(f"{BASE}/workbooks", json={"name": "x", "path": "/etc/x.xlsx"})
    assert outside.status_code == 400


def test_write_validation(client: TestClient) -> None:
    seed()
    url = f"{BASE}/workbooks/budget/write"
    assert client.post(url, content=b"not json").status_code == 400
    assert client.post(url, json=[1]).status_code == 400
    assert "missing required" in client.post(url, json={"values": [[1]]}).json()["error"]
    assert "formulas" in client.post(url, json={"start": "A1", "values": [["=1"]]}).json()["error"]
    assert client.post(url, json={"start": "A1", "values": [[1]], "scope": 5}).status_code == 400
    big = client.post(url, content=b'{"start":"A1","values":[["' + b"x" * 300_000 + b'"]]}')
    assert big.status_code == 413
    bad_sheets = client.post(f"{BASE}/workbooks", json={"name": "q", "path": "q.xlsx", "sheets": 1})
    assert bad_sheets.status_code == 400
    bad_scope = client.post(f"{BASE}/workbooks/budget/append", json={"scope": "x", "rows": [[1]]})
    assert bad_scope.status_code == 400
    assert client.post(f"{BASE}/workbooks/nope/append", json={"rows": [[1]]}).status_code == 404

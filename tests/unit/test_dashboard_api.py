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
    assert missing.status_code == 400
    assert "no workbook" in missing.json()["error"]
    wrong_scope = client.get(f"{BASE}/workbooks/budget/sheets", params={"scope": "global"})
    assert wrong_scope.status_code == 400
    assert client.get(f"{BASE}/workbooks/{'n' * 80}/sheets").status_code == 400
    too_long = client.get(f"{BASE}/workbooks/budget/data", params={"sheet": "s" * 200})
    assert "too long" in too_long.json()["error"]
    long_range = client.get(f"{BASE}/workbooks/budget/data", params={"range": "A" * 100})
    assert "too long" in long_range.json()["error"]
    bad_sheet = client.get(f"{BASE}/workbooks/budget/data", params={"sheet": "Nope"})
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
    assert response.json() == {"ok": False, "error": "internal error"}


def test_routes_are_read_only(client: TestClient) -> None:
    assert client.post(f"{BASE}/workbooks").status_code == 405
    assert client.delete(f"{BASE}/workbooks/budget/sheets").status_code in (404, 405)

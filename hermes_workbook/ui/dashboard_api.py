"""Read-only FastAPI routes for the Hermes dashboard "Workbooks" tab.

Mounted by Hermes at ``/api/plugins/hermes-workbook/``. Routes only read: they list
registered workbooks, sheet names and cell data. Writes stay with the agent tools.
Blocking file work runs in a worker thread. Error text from files or libraries is
never echoed to the browser; only the plugin's own user-facing messages are.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .. import registry
from ..backends import LocalBackend, WorkbookError
from ..plugin import workbook_status

__all__ = ["router"]

_LOG = logging.getLogger(__name__)
router = APIRouter()

MAX_NAME_LENGTH = 64
MAX_SHEET_LENGTH = 128
MAX_RANGE_LENGTH = 64


def _entry(name: str, scope: str | None) -> registry.Entry:
    if len(name) > MAX_NAME_LENGTH:
        raise registry.RegistryError("name too long")
    if scope is None:
        return registry.lookup(name)
    for entry in registry.list_entries(scope):
        if entry.name == name:
            return entry
    raise registry.RegistryError(f"no workbook named {name!r} in scope {scope!r}")


async def _run(operation: Callable[[], dict[str, Any]]) -> JSONResponse:
    try:
        payload = await asyncio.to_thread(operation)
    except (registry.RegistryError, WorkbookError) as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    except Exception:
        _LOG.exception("workbook dashboard request failed")
        return JSONResponse({"ok": False, "error": "internal error"}, status_code=500)
    return JSONResponse({"ok": True, **payload})


@router.get("/status")
async def status() -> JSONResponse:
    return await _run(lambda: dict(json.loads(workbook_status())))


@router.get("/workbooks")
async def list_workbooks(scope: str | None = None) -> JSONResponse:
    def op() -> dict[str, Any]:
        entries = registry.list_entries(scope)
        return {
            "workbooks": [
                {
                    "name": e.name,
                    "scope": e.scope,
                    "kind": e.kind,
                    "file": Path(e.path).name,
                    "exists": Path(e.path).is_file(),
                }
                for e in entries
            ]
        }

    return await _run(op)


@router.get("/workbooks/{name}/sheets")
async def workbook_sheets(name: str, scope: str | None = None) -> JSONResponse:
    return await _run(lambda: {"sheets": LocalBackend(Path(_entry(name, scope).path)).sheets()})


@router.get("/workbooks/{name}/data")
async def workbook_data(
    name: str,
    scope: str | None = None,
    sheet: str | None = None,
    range: str | None = None,  # noqa: A002 - query parameter name is part of the API
) -> JSONResponse:
    def op() -> dict[str, Any]:
        if sheet is not None and len(sheet) > MAX_SHEET_LENGTH:
            raise WorkbookError("sheet name too long")
        if range is not None and len(range) > MAX_RANGE_LENGTH:
            raise WorkbookError("range too long")
        backend = LocalBackend(Path(_entry(name, scope).path))
        return backend.read(sheet, range)

    return await _run(op)

"""FastAPI routes for the Hermes dashboard "Workbooks" tab and native clients.

Mounted by Hermes at ``/api/plugins/hermes-workbook/``. The contract is documented in
``docs/design/dashboard-api.md``. Reads: status, workbooks, sheets, data. Writes: create,
write, append, guarded by an optimistic ``if_revision`` token (409 on conflict).

Blocking file work runs in a worker thread. Error text from files or libraries is never
echoed to the client; only the plugin's own user-facing messages are. Every failure has the
shape ``{"ok": false, "code": <code>, "error": <message>}``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
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
MAX_BODY_BYTES = 256 * 1024
MAX_PATH_LENGTH = 256

_WRITE_LOCK = threading.Lock()


class ConflictError(Exception):
    """``if_revision`` did not match the file's current revision."""

    def __init__(self, revision: str) -> None:
        super().__init__("workbook changed since it was read")
        self.revision = revision


class BadRequestError(Exception):
    """Malformed request body or parameter."""


def _entry(name: str, scope: str | None) -> registry.Entry:
    if len(name) > MAX_NAME_LENGTH:
        raise BadRequestError("name too long")
    if scope is None:
        return registry.lookup(name)
    if scope not in registry.SCOPES:
        raise BadRequestError(f"unknown scope {scope!r}")
    for entry in registry.list_entries(scope):
        if entry.name == name:
            return entry
    raise registry.NotFoundError(f"no workbook named {name!r} in scope {scope!r}")


def _failure(code: str, message: str, status: int, **extra: Any) -> JSONResponse:
    return JSONResponse({"ok": False, "code": code, "error": message, **extra}, status_code=status)


async def _run(operation: Callable[[], dict[str, Any]]) -> JSONResponse:
    try:
        payload = await asyncio.to_thread(operation)
    except ConflictError as exc:
        return _failure("conflict", str(exc), 409, revision=exc.revision)
    except registry.NotFoundError as exc:
        return _failure("not_found", str(exc), 404)
    except (registry.RegistryError, WorkbookError, BadRequestError) as exc:
        return _failure("bad_request", str(exc), 400)
    except Exception:
        _LOG.exception("workbook dashboard request failed")
        return _failure("internal", "internal error", 500)
    return JSONResponse({"ok": True, **payload})


async def _body(request: Request) -> dict[str, Any] | JSONResponse:
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        return _failure("bad_request", "request body too large", 413)
    try:
        decoded = json.loads(raw or b"{}")
    except (ValueError, UnicodeDecodeError):
        return _failure("bad_request", "body must be valid JSON", 400)
    if not isinstance(decoded, dict):
        return _failure("bad_request", "body must be a JSON object", 400)
    return decoded


def _text(body: dict[str, Any], key: str, limit: int) -> str | None:
    value = body.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > limit:
        raise BadRequestError(f"{key!r} must be a string of at most {limit} characters")
    return value


def _required_text(body: dict[str, Any], key: str, limit: int) -> str:
    value = _text(body, key, limit)
    if value is None:
        raise BadRequestError(f"missing required field {key!r}")
    return value


def _check_revision(backend: LocalBackend, body: dict[str, Any]) -> None:
    expected = _text(body, "if_revision", 64)
    if expected is not None and expected != backend.revision():
        raise ConflictError(backend.revision())


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


@router.post("/workbooks")
async def create_workbook(request: Request) -> JSONResponse:
    body = await _body(request)
    if isinstance(body, JSONResponse):
        return body

    def op() -> dict[str, Any]:
        name = _required_text(body, "name", MAX_NAME_LENGTH)
        path = _required_text(body, "path", MAX_PATH_LENGTH)
        scope = _text(body, "scope", 16) or "profile"
        sheets = body.get("sheets")
        if sheets is not None and (
            not isinstance(sheets, list) or not all(isinstance(s, str) for s in sheets)
        ):
            raise BadRequestError("'sheets' must be a list of strings")
        resolved = registry.resolve_path(scope, path)
        backend = LocalBackend(resolved)
        backend.create(sheets)
        entry = registry.register(name, str(resolved), scope)
        return {"name": entry.name, "scope": entry.scope, "revision": backend.revision()}

    return await _run(op)


@router.get("/workbooks/{name}/sheets")
async def workbook_sheets(name: str, scope: str | None = None) -> JSONResponse:
    def op() -> dict[str, Any]:
        backend = LocalBackend(Path(_entry(name, scope).path))
        return {"sheets": backend.sheets(), "revision": backend.revision()}

    return await _run(op)


@router.get("/workbooks/{name}/data")
async def workbook_data(
    name: str,
    scope: str | None = None,
    sheet: str | None = None,
    range: str | None = None,  # noqa: A002 - query parameter name is part of the API
) -> JSONResponse:
    def op() -> dict[str, Any]:
        if sheet is not None and len(sheet) > MAX_SHEET_LENGTH:
            raise BadRequestError("sheet name too long")
        if range is not None and len(range) > MAX_RANGE_LENGTH:
            raise BadRequestError("range too long")
        backend = LocalBackend(Path(_entry(name, scope).path))
        result = backend.read(sheet, range)
        result["revision"] = backend.revision()
        return result

    return await _run(op)


@router.post("/workbooks/{name}/write")
async def workbook_write(name: str, request: Request) -> JSONResponse:
    body = await _body(request)
    if isinstance(body, JSONResponse):
        return body

    def op() -> dict[str, Any]:
        sheet = _text(body, "sheet", MAX_SHEET_LENGTH)
        start = _required_text(body, "start", 16)
        values = body.get("values")
        backend = LocalBackend(Path(_entry(name, _text(body, "scope", 16)).path))
        with _WRITE_LOCK:
            _check_revision(backend, body)
            written = backend.write(sheet, start, values)  # type: ignore[arg-type]
            return {"cells_written": written, "revision": backend.revision()}

    return await _run(op)


@router.post("/workbooks/{name}/append")
async def workbook_append(name: str, request: Request) -> JSONResponse:
    body = await _body(request)
    if isinstance(body, JSONResponse):
        return body

    def op() -> dict[str, Any]:
        sheet = _text(body, "sheet", MAX_SHEET_LENGTH)
        rows = body.get("rows")
        backend = LocalBackend(Path(_entry(name, _text(body, "scope", 16)).path))
        with _WRITE_LOCK:
            _check_revision(backend, body)
            appended = backend.append(sheet, rows)  # type: ignore[arg-type]
            return {"rows_appended": appended, "revision": backend.revision()}

    return await _run(op)

"""Tool handlers and schemas. Handlers return JSON strings; errors are ``{"error": ...}``."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import registry
from .backends import LocalBackend, WorkbookError

Handler = Callable[..., str]
_SCOPE_PROP = {
    "type": "string",
    "enum": ["profile", "global"],
    "description": "profile = private to the active Hermes profile; global = shared by all.",
}
_NAME_PROP = {"type": "string", "description": "Registered workbook name."}
_SHEET_PROP = {"type": "string", "description": "Sheet name; defaults to the active sheet."}
_ROWS_PROP = {
    "type": "array",
    "items": {"type": "array", "items": {"type": ["string", "number", "boolean", "null"]}},
    "description": "Rows of cell values. Formulas (leading '=') are rejected.",
}


def _ok(**payload: Any) -> str:
    return json.dumps({"ok": True, **payload}, sort_keys=True)


def _err(message: str) -> str:
    return json.dumps({"ok": False, "error": message})


def _guard(fn: Callable[[dict[str, Any]], str]) -> Handler:
    def wrapper(args: dict[str, Any] | None = None, **_kwargs: Any) -> str:
        try:
            return fn(args or {})
        except (registry.RegistryError, WorkbookError) as exc:
            return _err(str(exc))
        except KeyError as exc:
            return _err(f"missing required argument {exc}")

    return wrapper


def _backend(name: str) -> LocalBackend:
    return LocalBackend(Path(registry.lookup(name).path))


def _scope(args: dict[str, Any]) -> str:
    return str(args.get("scope", "profile"))


@_guard
def workbook_register(args: dict[str, Any]) -> str:
    entry = registry.register(args["name"], args["path"], _scope(args))
    return _ok(name=entry.name, path=entry.path, scope=entry.scope)


@_guard
def workbook_unregister(args: dict[str, Any]) -> str:
    return _ok(removed=registry.unregister(args["name"], _scope(args)))


@_guard
def workbook_list(args: dict[str, Any]) -> str:
    scope = args.get("scope")
    entries = registry.list_entries(str(scope) if scope else None)
    return _ok(
        workbooks=[
            {"name": e.name, "path": e.path, "kind": e.kind, "scope": e.scope} for e in entries
        ]
    )


@_guard
def workbook_create(args: dict[str, Any]) -> str:
    scope = _scope(args)
    path = registry.resolve_path(scope, args["path"])
    LocalBackend(path).create(args.get("sheets"))
    entry = registry.register(args["name"], str(path), scope)
    return _ok(name=entry.name, path=entry.path, scope=scope)


@_guard
def workbook_sheets(args: dict[str, Any]) -> str:
    return _ok(sheets=_backend(args["name"]).sheets())


@_guard
def workbook_read(args: dict[str, Any]) -> str:
    return _ok(**_backend(args["name"]).read(args.get("sheet"), args.get("range")))


@_guard
def workbook_write(args: dict[str, Any]) -> str:
    cells = _backend(args["name"]).write(args.get("sheet"), args["start"], args["values"])
    return _ok(cells_written=cells)


@_guard
def workbook_append(args: dict[str, Any]) -> str:
    return _ok(rows_appended=_backend(args["name"]).append(args.get("sheet"), args["rows"]))


def _schema(
    name: str, description: str, props: dict[str, Any], required: list[str]
) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": props,
            "required": required,
            "additionalProperties": False,
        },
    }


TOOLS: list[tuple[str, str, Handler, dict[str, Any]]] = [
    (
        "workbook_register",
        "Register an existing .xlsx/.csv file under a name so other workbook tools can use it.",
        workbook_register,
        _schema(
            "workbook_register",
            "Register an existing .xlsx/.csv file under a name so other workbook tools can use it. "
            "Relative paths live in the scope's workbook directory.",
            {"name": _NAME_PROP, "path": {"type": "string"}, "scope": _SCOPE_PROP},
            ["name", "path"],
        ),
    ),
    (
        "workbook_unregister",
        "Remove a workbook name from the registry (the file is not deleted).",
        workbook_unregister,
        _schema(
            "workbook_unregister",
            "Remove a workbook name from the registry. The file is not deleted.",
            {"name": _NAME_PROP, "scope": _SCOPE_PROP},
            ["name"],
        ),
    ),
    (
        "workbook_list",
        "List registered workbooks in both scopes (profile first).",
        workbook_list,
        _schema(
            "workbook_list",
            "List registered workbooks. Omit scope to list both scopes.",
            {"scope": _SCOPE_PROP},
            [],
        ),
    ),
    (
        "workbook_create",
        "Create a new empty .xlsx/.csv workbook and register it.",
        workbook_create,
        _schema(
            "workbook_create",
            "Create a new empty .xlsx or .csv workbook and register it. Fails if the file exists.",
            {
                "name": _NAME_PROP,
                "path": {"type": "string"},
                "scope": _SCOPE_PROP,
                "sheets": {"type": "array", "items": {"type": "string"}},
            },
            ["name", "path"],
        ),
    ),
    (
        "workbook_sheets",
        "List sheet names in a workbook.",
        workbook_sheets,
        _schema(
            "workbook_sheets", "List sheet names in a workbook.", {"name": _NAME_PROP}, ["name"]
        ),
    ),
    (
        "workbook_read",
        "Read cells from a workbook as rows.",
        workbook_read,
        _schema(
            "workbook_read",
            "Read cells as rows. 'range' is A1 notation such as A1:C10; omit for the used range. "
            "Output is capped and flagged truncated.",
            {"name": _NAME_PROP, "sheet": _SHEET_PROP, "range": {"type": "string"}},
            ["name"],
        ),
    ),
    (
        "workbook_write",
        "Write values into an xlsx workbook starting at a cell.",
        workbook_write,
        _schema(
            "workbook_write",
            "Write rows of values into an .xlsx workbook with the top-left at 'start' (e.g. B2).",
            {
                "name": _NAME_PROP,
                "sheet": _SHEET_PROP,
                "start": {"type": "string"},
                "values": _ROWS_PROP,
            },
            ["name", "start", "values"],
        ),
    ),
    (
        "workbook_append",
        "Append rows after the last used row.",
        workbook_append,
        _schema(
            "workbook_append",
            "Append rows after the last used row of a sheet (or csv file).",
            {"name": _NAME_PROP, "sheet": _SHEET_PROP, "rows": _ROWS_PROP},
            ["name", "rows"],
        ),
    ),
]

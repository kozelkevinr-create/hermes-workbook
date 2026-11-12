"""Workbook registry: named workbooks per scope (profile or global).

Each scope has its own SQLite database under the Hermes plugin data directory.
Lookup by name checks the profile scope first, then the global scope.
This module is the only place that writes SQL.
"""

from __future__ import annotations

import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from .plugin_storage import global_dir, open_db, profile_dir

PLUGIN_NAME = "hermes-workbook"
PROFILE_DB_FILENAME = "workbook.db"
GLOBAL_DB_FILENAME = "workbook-global.db"
ROOTS_ENV = "HERMES_WORKBOOK_ROOTS"
SCOPES = ("profile", "global")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS workbooks (
    name TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'local',
    created_at INTEGER NOT NULL
)
"""


class RegistryError(Exception):
    """A user-facing registry failure (bad scope, name, or path)."""


class NotFoundError(RegistryError):
    """The named workbook is not registered."""


@dataclass(frozen=True)
class Entry:
    name: str
    path: str
    kind: str
    scope: str


def scope_dir(scope: str) -> Path:
    """Data directory for ``scope``. Resolved on every call (profiles can switch)."""
    if scope == "profile":
        return profile_dir(PLUGIN_NAME)
    if scope == "global":
        return global_dir(PLUGIN_NAME)
    raise RegistryError(f"unknown scope {scope!r}; use one of {', '.join(SCOPES)}")


def workbooks_root(scope: str) -> Path:
    """Default directory for workbook files in ``scope``."""
    root = scope_dir(scope) / "workbooks"
    root.mkdir(parents=True, exist_ok=True)
    return root


def allowed_roots(scope: str) -> list[Path]:
    """Directories workbook files may live under: the scope root plus env extras."""
    roots = [workbooks_root(scope).resolve()]
    for raw in os.environ.get(ROOTS_ENV, "").split(os.pathsep):
        if raw.strip():
            roots.append(Path(raw).expanduser().resolve())
    return roots


def resolve_path(scope: str, path: str) -> Path:
    """Resolve ``path`` (relative paths live in the scope root) and enforce the roots."""
    if not path or "\x00" in path:
        raise RegistryError("path is empty or invalid")
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = workbooks_root(scope) / candidate
    resolved = candidate.resolve()
    for root in allowed_roots(scope):
        if resolved == root or root in resolved.parents:
            return resolved
    raise RegistryError(f"path is outside the allowed roots; set {ROOTS_ENV} to allow more")


def _db_path(scope: str) -> Path:
    filename = PROFILE_DB_FILENAME if scope == "profile" else GLOBAL_DB_FILENAME
    return scope_dir(scope) / filename


def _connect(scope: str) -> sqlite3.Connection:
    conn = open_db(_db_path(scope))
    conn.execute(_SCHEMA)
    return conn


def register(name: str, path: str, scope: str) -> Entry:
    """Register (or replace) ``name`` in ``scope``."""
    name = name.strip()
    if not name or len(name) > 64 or not all(c.isalnum() or c in "-_." for c in name):
        raise RegistryError("name must be 1-64 chars of letters, digits, '-', '_' or '.'")
    resolved = resolve_path(scope, path)
    if not resolved.is_file():
        raise RegistryError(f"file does not exist: {resolved.name}")
    conn = _connect(scope)
    try:
        conn.execute(
            "INSERT INTO workbooks(name, path, kind, created_at) VALUES (?, ?, 'local', ?) "
            "ON CONFLICT(name) DO UPDATE SET path = excluded.path",
            (name, str(resolved), int(time.time())),
        )
    finally:
        conn.close()
    return Entry(name, str(resolved), "local", scope)


def unregister(name: str, scope: str) -> bool:
    """Remove ``name`` from ``scope``; the workbook file is left untouched."""
    conn = _connect(scope)
    try:
        cur = conn.execute("DELETE FROM workbooks WHERE name = ?", (name,))
        return cur.rowcount > 0
    finally:
        conn.close()


def list_entries(scope: str | None = None) -> list[Entry]:
    """List entries for one scope, or both (profile first)."""
    entries: list[Entry] = []
    for sc in (scope,) if scope else SCOPES:
        conn = _connect(sc)
        try:
            rows = conn.execute("SELECT name, path, kind FROM workbooks ORDER BY name").fetchall()
        finally:
            conn.close()
        entries.extend(Entry(r["name"], r["path"], r["kind"], sc) for r in rows)
    return entries


def lookup(name: str) -> Entry:
    """Find ``name``: profile scope overrides global."""
    for sc in SCOPES:
        for entry in list_entries(sc):
            if entry.name == name:
                return entry
    raise NotFoundError(f"no workbook named {name!r}")

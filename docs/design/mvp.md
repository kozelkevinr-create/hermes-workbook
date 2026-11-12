# MVP design: hermes-workbook

## Goal
Native Hermes plugin that lets an agent manage workbooks. Smallest useful slice first.

## MVP scope
- Local `.xlsx` (openpyxl) and `.csv` workbooks on the Hermes host.
- A registry of named workbooks so tools take a name, not a raw path.
- Two scopes: **global** (shared by all profiles) and **profile** (private to the active profile).
- Tools registered via `ctx.register_tool`:
  - `workbook_register(name, path, scope)` / `workbook_unregister(name, scope)` / `workbook_list()`
  - `workbook_create(name, path, scope, sheets?)`
  - `workbook_sheets(name)`
  - `workbook_read(name, sheet, range)` -> rows as lists
  - `workbook_write(name, sheet, range, values)`
  - `workbook_append(name, sheet, rows)`
- Out of scope for MVP: Google Sheets, formulas evaluation, charts, formatting, Rust.

## Scope resolution
- Registry per scope stored via shared `plugin_storage` (`profile_dir`, `global_dir`), small SQLite table `workbooks(name, path, scope)`.
- Lookup by name: profile scope first, then global (profile overrides global on name clash). `workbook_list` shows both with a scope column.
- Writes to a global-scope workbook allowed from any profile; revisit permissions after MVP.
- Do not cache the profile dir across calls (active profile can change).

## Safety
- Paths must be absolute or resolved against a configurable `workbooks_root`; reject paths outside registered roots to keep agents from touching arbitrary files.
- Write tools save atomically (write temp file, then rename).
- Cap rows/cells returned per read; report truncation.

## Backend interface
`Backend` protocol (`read`, `write`, `append`, `sheets`, `create`) with `LocalBackend` (openpyxl/csv). A later `GoogleSheetsBackend` plugs in, selected by registry entry `kind`. Registry schema includes `kind` now (`local`) to avoid a migration.

## Layout (after shared scaffold lands)
plugin.yaml, __init__.py (register), hermes_workbook/{plugin_storage.py (shared, verbatim), registry.py, backends/, tools.py}, tests/, docs/.

## Open items (not blocking)
- Verify global_dir works under plugins.isolation: host (calendar session tracking).
- Google auth model (needs Kevin: OAuth credentials) after MVP.

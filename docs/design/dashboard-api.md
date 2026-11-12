# Dashboard / native-client JSON API

Mounted by the Hermes dashboard at `/api/plugins/hermes-workbook/`. Used by the web tab and
native clients (the Hermes Android app). Requires whatever auth the dashboard requires
(session token header or login cookie); the plugin adds none of its own.

Everything is JSON. Success: HTTP 200 and `{"ok": true, ...}`. Failure:
`{"ok": false, "code": "<code>", "error": "<message>"}` with the HTTP status below. Error
text is the plugin's own message; internal exception text is never returned.

| code | HTTP | meaning |
|---|---|---|
| `bad_request` | 400 (413 for an oversized body) | invalid parameter, body, sheet, range, path or value |
| `not_found` | 404 | no workbook with that name (in that scope) |
| `conflict` | 409 | `if_revision` is stale; response also carries the current `revision` |
| `internal` | 500 | unexpected failure |

## Profile and scope
`scope` is `profile` (private to the profile the dashboard process runs as) or `global`
(shared by all profiles). Name lookup without `scope` checks profile first, then global. A
`?profile=<name>` query parameter is ignored by the plugin; whether it changes which profile
answers depends on the Hermes host. Clients must not assume it does.

## Revision tokens
Reads return `revision`, an opaque string that changes whenever the file changes. Writes take
an optional `if_revision`: if present and not equal to the current revision the write is
refused with 409 and nothing changes. Clients should send the revision they last read, show
the conflict, reload (using the returned `revision`) and let the user retry.

## Routes

### GET /status
`{"ok": true, "plugin": "hermes-workbook", "version": "0.0.1", "profile_data_dir": "...",
"global_data_dir": "...", "databases": {...}, "shared_store": {"ok": true, "shared": null,
"peers_seen": [], "writable": true, "detail": "..."}}`. Clients can use `GET /status` as a
capability probe: a 404 means the plugin is not installed.

### GET /workbooks?scope=profile|global
`{"ok": true, "workbooks": [{"name": "budget", "scope": "profile", "kind": "local",
"file": "budget.xlsx", "exists": true}]}`. Both scopes (profile first) when `scope` is omitted.
`file` is a file name only, never a path.

### POST /workbooks  (create)
Body `{"name": "budget", "path": "budget.xlsx", "scope": "profile", "sheets": ["A", "B"]}`
(`scope`, `sheets` optional; `.xlsx` or `.csv` only; relative paths live in the scope's
workbook directory). Response `{"ok": true, "name": "budget", "scope": "profile",
"revision": "..."}`. 400 if the file exists, the path is outside the allowed roots, or the
name is invalid.

### GET /workbooks/{name}/sheets?scope=
`{"ok": true, "sheets": ["A", "B"], "revision": "..."}`. A csv workbook has one sheet,
`"Sheet1"`.

### GET /workbooks/{name}/data?scope=&sheet=&range=
`sheet` defaults to the active sheet; `range` is A1 notation (`A1:C10`), xlsx only. Response
`{"ok": true, "rows": [["item", "qty"], ["apple", 3]], "row_count": 2, "truncated": false,
"revision": "..."}`. Cells are string, number, boolean or null (csv cells are strings).
Output is capped at 5000 cells; `truncated` is true when rows were dropped.

### POST /workbooks/{name}/write
Body `{"scope": "profile", "sheet": "A", "start": "B2", "values": [[1, "x"], [2.5, null]],
"if_revision": "..."}` (`scope`, `sheet`, `if_revision` optional). Writes values with the
top-left at `start`. Response `{"ok": true, "cells_written": 4, "revision": "..."}`. xlsx only
(400 for csv). Formulas (strings starting with `=`) are rejected.

### POST /workbooks/{name}/append
Body `{"scope": "profile", "sheet": "A", "rows": [["pear", 5]], "if_revision": "..."}`.
Response `{"ok": true, "rows_appended": 1, "revision": "..."}`. Works for xlsx and csv.

Limits: request bodies up to 256 KiB; at most 5000 cells per call; names 64 chars.

## Not installed / older plugin versions
Plugin versions before this contract had only the four read routes and no `revision` field,
and returned 400 (not 404) for an unknown workbook with no `code`. Clients should treat a
missing `revision` as "no conflict checking" and a 404/405 on a POST as "read-only".

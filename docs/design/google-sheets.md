# Google Sheets backend design (post-MVP, not started)

Status: design only. Blocked on Google credentials from Kevin. Nothing here is implemented.

## Goal
Register a Google Sheet under a name (`kind = "gsheets"`) and use the same nine tools
(`workbook_read/write/append/sheets/...`) against it, in global or profile scope.

## Backend interface
The registry already stores `kind`. `LocalBackend` (read, write, append, sheets, create) becomes
one implementation of a `Backend` protocol; `tools._backend(name)` picks by `entry.kind`.
`path` holds the spreadsheet ID (or URL, normalised to ID on register) for `gsheets`.

## Dependencies
Prefer plain HTTPS (`urllib`) against the Sheets v4 REST API plus a token helper, to keep the
dependency list at `openpyxl` only. `google-auth` + `google-api-python-client` are the fallback if
token handling grows. Decide when implementing; log in DECISIONS.md.

## Auth options (decision needed from Kevin: needs his Google account/project)
| Option | Fits a headless Hermes host | Notes |
|---|---|---|
| Service account | Yes, simplest | Key JSON on the host; user shares each sheet with the SA email. No consent screen, no token refresh. One identity for all profiles unless keys are per profile. |
| OAuth, loopback + PKCE | Needs a browser path to the VM (SSH port forward) | Acts as the user; refresh token stored per profile. Calendar plugin plans the same flow; share code. |
| OAuth, device flow | Yes | Google restricts device-flow scopes; verify that a Sheets-capable scope (e.g. `drive.file`) is allowed before choosing. |

Recommendation: service account for the first release (works unattended, least moving parts),
OAuth loopback later for "my own sheets" use. Both fit behind one `TokenProvider` interface.

## Credential storage and scopes
- Secrets are references, never values in SQLite, logs or the repo (CLAUDE.md rule 7).
- Per-profile credentials live under `profile_dir()`; a global credential under `global_dir()`
  with file mode 0600. Profile credentials override global, mirroring workbook lookup.
- Requested scope: `https://www.googleapis.com/auth/spreadsheets` (add `drive.file` only if
  `create` is supported).

## Behaviour and limits
- Same JSON result shape and 5000-cell cap as local tools; reject formulas on write (use
  `valueInputOption=RAW`, which also stops formula evaluation).
- Map API errors (403 not shared, 404, 429 rate limit) to clear `{"ok": false, "error": ...}`
  messages, with bounded retry on 429/5xx.
- Ranges use A1 notation natively, so csv's "no ranges" limitation does not apply.
- No network in unit tests: inject a fake HTTP transport; integration tests are opt-in
  (`-m integration`) and need real credentials.

## Open questions for Kevin (batch, one message)
1. Which Google account/project, and is a service account acceptable?
2. One credential for all profiles, or one per profile?
3. Should `workbook_create` be supported for Sheets (needs Drive scope)?

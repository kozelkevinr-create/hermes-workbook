# Decisions

One line each: date, decision, why.

- 2026-11-12: Python >=3.11, uv + pyproject.toml, ruff + pytest, flat layout, no Rust. Shared stack with hermes-calendar-plugin, approved by Kevin.
- 2026-11-12: Git flow main/stage/test, feature/* cut from test. Matches calendar plugin; Kevin approves moves to stage and main.
- 2026-11-12: MVP is local xlsx/csv only via openpyxl; Google Sheets deferred. Avoids OAuth credentials (needs Kevin's accounts) and keeps the first slice testable offline.
- 2026-11-12: Workbook files live on the Hermes host (docker-host), never assumed to exist on a dev machine. Plugin runs inside Hermes there; must stay publishable.
- 2026-11-12: Storage helper plugin_storage.py and CLAUDE.md are copied verbatim from hermes-calendar-plugin once merged there; not written here.
- 2026-11-12: Scaffold copied from hermes-calendar-plugin test branch (plugin_storage.py byte-identical; CLAUDE.md branch/worker/dispatch sections verbatim, domain sections renamed). Tool declared in plugin.yaml: workbook_status.
- 2026-11-12: openpyxl is the one runtime dependency (MVP xlsx backend). Hermes host must have it installed; revisit vendoring/install hook before publishing.
- 2026-11-12: Scaffold done by coordinator directly rather than a worker: it was mechanical copy/rename and cheaper than a task spec.
- 2026-11-12: Root __init__.py and the package use relative imports (Hermes loads the plugin dir as a package; absolute imports fail in `hermes plugins validate`). Reported by hermes-calendar-plugin.
- 2026-11-12: pytest must run with `--rootdir=tests tests` plus `--import-mode=importlib` (pyproject addopts; Makefile/CI pass rootdir): otherwise pytest imports the root __init__.py as a package and fails on its relative import. Added tests/unit/test_hermes_load.py to load the plugin like Hermes does.
- 2026-11-12: Workbook files must live under the scope's `workbooks/` dir or a root listed in env HERMES_WORKBOOK_ROOTS (os.pathsep-separated). Why: keeps agents from touching arbitrary host files; env var needs no extra config schema. Revisit as a plugin config option.
- 2026-11-12: MVP rejects formulas (cell values starting with "=") on write. Why: avoids formula injection and unverifiable computed values; revisit post-MVP.
- 2026-11-12: workbook_register requires the file to exist; workbook_create makes the file and registers it. csv has one pseudo-sheet "Sheet1", no ranges, append only.
- 2026-11-12: Read/write capped at 5000 cells per call; reads flag `truncated`.
- 2026-11-12: Added types-openpyxl to dev deps for mypy --strict.
- 2026-11-12: Adopted calendar's root __init__.py (relative import, bare-package fallback), scripts/validate_remote.sh, `make validate-remote` and tests/unit/test_relative_imports.py. Dropped the `--rootdir=tests`/importlib pytest workaround; bare `pytest` works. Real `hermes plugins validate --json` on docker-host: ok:true, all 9 tools match registrations, isolation verdict host.
- 2026-11-12: openpyxl is imported lazily, so the validator does not prove it is installed on the Hermes host. Still to verify/handle (install hook or clear error message).
- 2026-11-12: openpyxl stays a declared pyproject dependency: Hermes reads [project].dependencies and installs it at 'hermes plugins install' with consent (verified in hermes pm/plugin_declarations.py). Missing at runtime -> tool error telling user to run 'hermes pm repair'. csv does not need it.

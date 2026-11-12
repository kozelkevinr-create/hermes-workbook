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

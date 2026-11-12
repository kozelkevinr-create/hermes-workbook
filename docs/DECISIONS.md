# Decisions

One line each: date, decision, why.

- 2026-11-12: Python >=3.11, uv + pyproject.toml, ruff + pytest, flat layout, no Rust. Shared stack with hermes-calendar-plugin, approved by Kevin.
- 2026-11-12: Git flow main/stage/test, feature/* cut from test. Matches calendar plugin; Kevin approves moves to stage and main.
- 2026-11-12: MVP is local xlsx/csv only via openpyxl; Google Sheets deferred. Avoids OAuth credentials (needs Kevin's accounts) and keeps the first slice testable offline.
- 2026-11-12: Workbook files live on the Hermes host (docker-host), never assumed to exist on a dev machine. Plugin runs inside Hermes there; must stay publishable.
- 2026-11-12: Storage helper plugin_storage.py and CLAUDE.md are copied verbatim from hermes-calendar-plugin once merged there; not written here.

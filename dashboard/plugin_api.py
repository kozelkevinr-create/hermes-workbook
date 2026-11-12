"""Dashboard backend entry point for the workbook plugin.

Hermes imports this file by path (not as a package) and mounts its ``router`` at
``/api/plugins/hermes-workbook/``. It is not imported by ``register()``, so FastAPI
stays an optional, dashboard-side dependency. The routes live in
:mod:`hermes_workbook.ui.dashboard_api`; this bridge only makes the package
importable and re-exports the router.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PLUGIN_ROOT = str(Path(__file__).resolve().parents[1])
if _PLUGIN_ROOT not in sys.path:
    # Append (never prepend) so the stdlib and the dashboard's packages keep priority.
    sys.path.append(_PLUGIN_ROOT)

from hermes_workbook.ui.dashboard_api import router  # noqa: E402 - path bootstrap above

__all__ = ["router"]

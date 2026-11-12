"""Load the plugin the way Hermes does: as a package, with a clean sys.path."""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

LOADER = textwrap.dedent(
    """
    import importlib.util, sys
    spec = importlib.util.spec_from_file_location(
        "workbook_plugin",
        sys.argv[1] + "/__init__.py",
        submodule_search_locations=[sys.argv[1]],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    assert callable(module.register)
    print("loaded")
    """
)


def test_plugin_loads_as_package_without_repo_on_sys_path() -> None:
    result = subprocess.run(
        [sys.executable, "-I", "-c", LOADER, str(REPO_ROOT)],
        capture_output=True,
        text=True,
        check=False,
        cwd="/",
    )
    assert result.returncode == 0, result.stderr
    assert "loaded" in result.stdout

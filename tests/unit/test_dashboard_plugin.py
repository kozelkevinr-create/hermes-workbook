"""Static and load-time checks for the hand-written dashboard bundle."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD = REPO_ROOT / "dashboard"
MANIFEST = DASHBOARD / "manifest.json"
BUNDLE = DASHBOARD / "dist" / "index.js"
STYLESHEET = DASHBOARD / "dist" / "style.css"
API_FILE = DASHBOARD / "plugin_api.py"

FORBIDDEN_JS = (
    "innerHTML",
    "outerHTML",
    "insertAdjacentHTML",
    "dangerouslySetInnerHTML",
    "document.write",
    "eval(",
    "new Function(",
)


def test_manifest_matches_agent_plugin_and_points_at_real_files() -> None:
    manifest: Any = json.loads(MANIFEST.read_text(encoding="utf-8"))
    agent: Any = yaml.safe_load((REPO_ROOT / "plugin.yaml").read_text(encoding="utf-8"))
    assert manifest["name"] == agent["name"] == "hermes-workbook"
    assert manifest["tab"]["path"] == "/workbooks"
    for key in ("entry", "css", "api"):
        candidate = (DASHBOARD / manifest[key]).resolve()
        assert candidate.is_file()
        assert candidate.is_relative_to(DASHBOARD.resolve())


def test_bundle_uses_sdk_and_never_builds_dom_from_cell_text() -> None:
    source = BUNDLE.read_text(encoding="utf-8")
    assert "window.__HERMES_PLUGIN_SDK__" in source
    assert "window.__HERMES_PLUGINS__.register(PLUGIN_NAME, WorkbookPage)" in source
    assert "SDK.fetchJSON" in source
    assert 'PLUGIN_NAME = "hermes-workbook"' in source
    present = [token for token in FORBIDDEN_JS if token in source]
    assert not present, f"bundle uses forbidden DOM/JS escape hatch(es): {present}"
    assert "aria-live" in source
    assert "Profile (private)" in source
    assert "Shared (global)" in source


def test_bundle_is_read_only() -> None:
    source = BUNDLE.read_text(encoding="utf-8")
    for method in ('"POST"', '"PUT"', '"PATCH"', '"DELETE"'):
        assert method not in source


def test_stylesheet_exposes_focus_styles_and_theme_vars() -> None:
    source = STYLESHEET.read_text(encoding="utf-8")
    assert ":focus-visible" in source
    assert "--color-border" in source


def test_bridge_loads_without_repo_on_sys_path(tmp_path: Path) -> None:
    driver = """
import importlib.util, pathlib, sys
spec = importlib.util.spec_from_file_location("hermes_dashboard_plugin_isolated", pathlib.Path(sys.argv[1]))
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
print(sorted({route.path for route in module.router.routes}))
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", driver, str(API_FILE)],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert "/workbooks" in result.stdout
    assert "/status" in result.stdout


def test_bridge_exposes_router() -> None:
    spec = importlib.util.spec_from_file_location("hermes_dashboard_plugin_workbook_test", API_FILE)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    paths = {route.path for route in module.router.routes}
    assert {"/status", "/workbooks", "/workbooks/{name}/sheets", "/workbooks/{name}/data"} <= paths


def test_register_works_without_fastapi() -> None:
    driver = """
import builtins, sys
real = builtins.__import__
def blocked(name, *a, **k):
    if name == "fastapi" or name.startswith("fastapi."):
        raise ImportError("fastapi unavailable")
    return real(name, *a, **k)
builtins.__import__ = blocked
sys.path.insert(0, sys.argv[1])
import hermes_workbook.plugin as plugin
class Ctx:
    def register_tool(self, **kw): pass
plugin.register(Ctx())
print("register ok")
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", driver, str(REPO_ROOT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert "register ok" in result.stdout

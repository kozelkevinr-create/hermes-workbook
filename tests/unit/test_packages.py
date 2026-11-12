"""Smoke tests that every scaffold package imports."""

from __future__ import annotations

import importlib

import pytest

PACKAGES = [
    "hermes_workbook",
]


@pytest.mark.parametrize("package", PACKAGES)
def test_package_imports(package: str) -> None:
    assert importlib.import_module(package).__doc__

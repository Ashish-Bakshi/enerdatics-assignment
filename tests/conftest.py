"""Pytest configuration and fixtures for source watcher tests."""

import importlib.util
from pathlib import Path
import pytest


@pytest.fixture
def watcher_cli():
    """Load the watcher.py CLI script as a distinct module."""
    script_path = Path(__file__).resolve().parents[1] / "watcher.py"
    spec = importlib.util.spec_from_file_location("watcher_cli", script_path)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    return cli

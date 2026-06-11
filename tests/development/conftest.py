"""
Conftest for the development/ directory.

These tests are diagnostic scripts that make real API calls and require
configured credentials.  Mark them as skipped unless explicitly opted-in via
the --run-dev flag so `pytest` does not fail in CI.
"""
import pytest


def pytest_collection_modifyitems(config, items):
    """Skip all tests in this directory unless --run-dev is passed."""
    for item in items:
        if "development" in str(item.fspath):
            item.add_marker(
                pytest.mark.skip(reason="development/diagnostic test — requires real API keys")
            )

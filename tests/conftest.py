"""tests/conftest.py — pytest configuration, markers, and skip reporting."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "unit: Pure logic tests (no external deps)")
    config.addinivalue_line("markers", "integration: Tests needing embedding/LLM/workspace")
    config.addinivalue_line("markers", "e2e: End-to-end tests (local only)")


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Print skip reasons at the end of the test run."""
    skipped = terminalreporter.stats.get("skipped", [])
    if skipped:
        terminalreporter.write_sep("=", "SKIP REASONS")
        for rep in skipped:
            # pytest stores skip reason in longrepr
            longrepr = getattr(rep, "longrepr", "")
            if isinstance(longrepr, str):
                reason = longrepr.split("Skipped: ", 1)[-1] if "Skipped:" in longrepr else longrepr
            elif isinstance(longrepr, tuple) and len(longrepr) >= 3:
                # skipif format: (file, line, reason)
                reason = str(longrepr[2]).replace("Skipped: ", "")
            elif hasattr(longrepr, "reason"):
                reason = longrepr.reason
            else:
                reason = str(longrepr) if longrepr else "unknown"
            terminalreporter.write_line(f"  {rep.nodeid}: {reason}")

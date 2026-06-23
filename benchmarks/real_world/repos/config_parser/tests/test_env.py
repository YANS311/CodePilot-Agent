"""Tests for parser.env — environment variable overrides."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cfgparser.env import apply_env_overrides


class TestApplyEnvOverrides:
    def test_override_first_key(self):
        """First key IS overridden (this works due to the bug being partial)."""
        config = {"name": "original", "port": 8080}
        os.environ["APP_NAME"] = "overridden"
        try:
            result = apply_env_overrides(config, prefix="APP")
            assert result["name"] == "overridden"
        finally:
            del os.environ["APP_NAME"]

    def test_override_second_key(self):
        """BUG: second key is NOT overridden because only the first key
        is processed."""
        config = {"name": "myapp", "port": 8080}
        os.environ["APP_PORT"] = "9090"
        try:
            result = apply_env_overrides(config, prefix="APP")
            # BUG: port stays 8080 because only 'name' is processed
            assert result["port"] == 9090
        finally:
            del os.environ["APP_PORT"]

    def test_override_all_keys(self, monkeypatch):
        """BUG: only the first key gets the env override."""
        config = {"name": "myapp", "port": 8080, "debug": False}
        monkeypatch.setenv("APP_NAME", "overridden")
        monkeypatch.setenv("APP_PORT", "9090")
        monkeypatch.setenv("APP_DEBUG", "true")
        result = apply_env_overrides(config, prefix="APP")
        assert result["name"] == "overridden"
        assert result["port"] == 9090  # BUG: returns 8080
        assert result["debug"] is True  # BUG: returns False

    def test_no_env_vars(self):
        config = {"name": "myapp"}
        result = apply_env_overrides(config, prefix="APP")
        assert result == {"name": "myapp"}

    def test_empty_config(self):
        result = apply_env_overrides({}, prefix="APP")
        assert result == {}

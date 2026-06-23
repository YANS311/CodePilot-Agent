"""Tests for parser.loader — config file loading."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cfgparser.loader import load_config


class TestLoadConfig:
    def test_load_valid(self, tmp_path):
        cfg = {"name": "myapp", "version": "1.0", "debug": False}
        p = tmp_path / "config.json"
        p.write_text(json.dumps(cfg), encoding="utf-8")
        result = load_config(str(p))
        assert result == cfg

    def test_load_missing_file(self):
        """BUG: load_config raises FileNotFoundError instead of returning
        a structured error dict like {"error": "File not found"}."""
        result = load_config("/nonexistent/path.json")
        # BUG: should return {"error": "..."} but raises FileNotFoundError
        assert "error" in result

    def test_load_malformed_json(self, tmp_path):
        """BUG: load_config raises raw json.JSONDecodeError instead of
        returning a structured error dict."""
        p = tmp_path / "bad.json"
        p.write_text("{invalid json content", encoding="utf-8")
        result = load_config(str(p))
        # BUG: should return {"error": "..."} but raises JSONDecodeError
        assert "error" in result

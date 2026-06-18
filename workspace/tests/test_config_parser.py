"""Tests for config_parser module."""

import json
import os
import tempfile

from examples.config_parser import (
    parse_ini,
    parse_json_config,
    merge_configs,
    get_config_value,
    validate_config,
)


class TestParseIni:
    def test_simple(self):
        text = "key=value"
        assert parse_ini(text) == {"key": "value"}

    def test_multiple(self):
        text = "a=1\nb=2"
        assert parse_ini(text) == {"a": "1", "b": "2"}

    def test_comments(self):
        text = "# comment\na=1"
        assert parse_ini(text) == {"a": "1"}


class TestParseJsonConfig:
    def test_valid_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"key": "value"}, f)
            path = f.name
        try:
            result = parse_json_config(path)
            assert result == {"key": "value"}
        finally:
            os.unlink(path)

    def test_missing_file(self):
        result = parse_json_config("/nonexistent/path.json")
        assert result == {}


class TestMergeConfigs:
    def test_simple_merge(self):
        base = {"a": 1}
        override = {"b": 2}
        result = merge_configs(base, override)
        assert result == {"a": 1, "b": 2}

    def test_override(self):
        base = {"a": 1}
        override = {"a": 2}
        result = merge_configs(base, override)
        assert result == {"a": 2}

    def test_deep_merge(self):
        base = {"db": {"host": "localhost", "port": 5432}}
        override = {"db": {"port": 3306}}
        result = merge_configs(base, override)
        assert result["db"]["host"] == "localhost"
        assert result["db"]["port"] == 3306


class TestGetConfigValue:
    def test_simple_key(self):
        config = {"a": 1}
        assert get_config_value(config, "a") == 1

    def test_nested_key(self):
        config = {"db": {"host": "localhost"}}
        assert get_config_value(config, "db.host") == "localhost"

    def test_missing_key_with_default(self):
        config = {"a": 1}
        assert get_config_value(config, "b", "fallback") == "fallback"


class TestValidateConfig:
    def test_all_present(self):
        config = {"host": "localhost", "port": 5432}
        assert validate_config(config, ["host", "port"]) == []

    def test_missing(self):
        config = {"host": "localhost"}
        missing = validate_config(config, ["host", "port", "db"])
        assert sorted(missing) == ["db", "port"]

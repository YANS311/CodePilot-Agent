"""Tests for parser.validator — config validation."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cfgparser.validator import validate_config, type_check


class TestValidateConfig:
    def test_valid_config(self):
        config = {"name": "myapp", "version": "1.0", "debug": False}
        errors = validate_config(config)
        assert errors == []

    def test_missing_required_fields(self):
        """BUG: validate_config does not catch missing required fields
        because the required-field check is dead code."""
        config = {"name": "myapp"}  # missing 'version' and 'debug'
        errors = validate_config(config)
        # BUG: returns [] instead of listing missing fields
        assert len(errors) == 2

    def test_empty_config(self):
        """BUG: even an empty dict passes validation."""
        errors = validate_config({})
        # BUG: should report all 3 required fields missing
        assert len(errors) == 3


class TestTypeCheck:
    def test_valid_types(self):
        config = {"name": "myapp", "port": 8080}
        schema = {"name": "str", "port": "int"}
        errors = type_check(config, schema)
        assert errors == []

    def test_wrong_type_str(self):
        config = {"name": 123}
        schema = {"name": "str"}
        errors = type_check(config, schema)
        assert len(errors) == 1
        assert "should be str" in errors[0]

    def test_wrong_type_int(self):
        """BUG: type_check does not validate 'int' fields — only 'str'
        is handled. So port="not_a_number" passes validation."""
        config = {"port": "not_a_number"}
        schema = {"port": "int"}
        errors = type_check(config, schema)
        # BUG: returns [] instead of flagging the wrong type
        assert len(errors) == 1

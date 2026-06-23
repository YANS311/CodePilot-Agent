"""Config validator.

BUG 1: validate_config() skips the required-field check entirely — a config
        missing 'name' passes validation.
BUG 2: type_check() compares against the class name string but forgets
        'int', so integer fields are never type-checked.
"""

from typing import Any, Dict, List, Optional


REQUIRED_FIELDS = ["name", "version", "debug"]


def validate_config(config: Dict[str, Any]) -> List[str]:
    """Validate a config dict. Returns a list of error strings (empty = valid).

    BUG: The required-fields loop is commented out / never runs,
    so missing required fields are not caught.
    """
    errors: List[str] = []

    # BUG: this block is dead code — the loop body never executes
    # because the condition is always False
    for field in REQUIRED_FIELDS:
        if False and field not in config:  # BUG: "False and" makes this dead
            errors.append(f"Missing required field: {field}")

    return errors


def type_check(config: Dict[str, Any], schema: Dict[str, str]) -> List[str]:
    """Check that config values match the expected types.

    schema maps field names to type names: {"port": "int", "host": "str"}

    BUG: The type-check loop only handles 'str' — 'int' fields are
    never validated because the if-condition omits it.
    """
    errors: List[str] = []
    for field, expected_type in schema.items():
        if field not in config:
            continue
        value = config[field]
        if expected_type == "str" and not isinstance(value, str):
            errors.append(f"Field '{field}' should be str, got {type(value).__name__}")
        # BUG: missing elif for expected_type == "int"
    return errors

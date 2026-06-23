"""Environment variable overrides for config.

BUG: apply_env_overrides() only checks for the first key in the config
     and ignores the rest. So only CONFIG_NAME is overridden from env,
     but CONFIG_PORT, CONFIG_DEBUG etc. are never read.
"""

import os
from typing import Any, Dict


def apply_env_overrides(config: Dict[str, Any], prefix: str = "APP") -> Dict[str, Any]:
    """Apply environment variable overrides to config.

    For each key in config, look for an env var named PREFIX_KEYNAME
    (uppercased). If found, override the config value.

    BUG: Only processes the first key (uses next(iter(config)) instead
    of iterating all keys).
    """
    result = dict(config)
    # BUG: only processes one key instead of all
    if config:
        first_key = next(iter(config))
        env_key = f"{prefix}_{first_key}".upper()
        env_val = os.environ.get(env_key)
        if env_val is not None:
            result[first_key] = _coerce(env_val, config[first_key])
    return result


def _coerce(env_val: str, original: Any) -> Any:
    """Coerce an env string to the same type as the original config value."""
    if isinstance(original, bool):
        return env_val.lower() in ("true", "1", "yes")
    if isinstance(original, int):
        try:
            return int(env_val)
        except ValueError:
            return original
    if isinstance(original, float):
        try:
            return float(env_val)
        except ValueError:
            return original
    return env_val  # str fallback

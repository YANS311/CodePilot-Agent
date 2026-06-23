"""Config file loader.

BUG 1: load_config() does not check if file exists — raises FileNotFoundError
        instead of returning a clear error dict.
BUG 2: load_config() does not handle YAML parse errors — raw exception leaks
        to the caller instead of returning a structured error.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional


def load_config(path: str) -> Dict[str, Any]:
    """Load a JSON config file and return its contents.

    BUG 1: Does not verify the file exists before reading.
    BUG 2: Does not catch json.JSONDecodeError for malformed files.
    """
    filepath = Path(path)
    # BUG: missing if not filepath.exists() check
    raw = filepath.read_text(encoding="utf-8")
    return json.loads(raw)

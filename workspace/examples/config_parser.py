"""配置解析模块 — 包含多个 Bug 用于评测。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def parse_ini(text: str) -> dict[str, str]:
    """解析简单 INI 格式配置。"""
    config = {}
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, value = line.split("=", 1)
            config[key.strip()] = value.strip()
    return config


def parse_json_config(path: str) -> dict[str, Any]:
    """从 JSON 文件解析配置。"""
    p = Path(path)
    if not p.exists():
        return {}  # BUG: 应该抛出 FileNotFoundError
    return json.loads(p.read_text(encoding="utf-8"))


def merge_configs(
    base: dict[str, Any], override: dict[str, Any]
) -> dict[str, Any]:
    """合并两个配置字典，override 覆盖 base。"""
    result = base.copy()
    for key, value in override.items():
        if isinstance(value, dict) and key in result:
            result[key] = value  # BUG: 应该递归合并，而不是直接覆盖
        else:
            result[key] = value
    return result


def get_config_value(
    config: dict[str, Any], key: str, default: Any = None
) -> Any:
    """从嵌套配置中获取值，支持 dot notation（如 'db.host'）。"""
    keys = key.split(".")
    current = config
    for k in keys:
        if isinstance(current, dict) and k in current:
            current = current[k]
        else:
            return default  # BUG: 应该返回 default，但这里返回了 None
    return current


def validate_config(config: dict[str, Any], required: list[str]) -> list[str]:
    """验证配置是否包含所有必需字段。返回缺失字段列表。"""
    missing = []
    for key in required:
        if key not in config:
            missing.append(key)
    return missing  # BUG: 应该返回 missing，但函数签名暗示返回空列表表示成功

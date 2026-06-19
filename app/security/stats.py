"""stats.py — Security 安全统计。"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from app.security.taxonomy import RiskType


@dataclass
class SecurityStats:
    """安全统计 — 线程安全的全局统计。"""

    blocked_requests: int = 0
    risk_distribution: dict[str, int] = field(default_factory=dict)
    prompt_injection_count: int = 0
    total_checks: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record_check(self, blocked: bool, risk_type: RiskType | None = None) -> None:
        """记录一次安全检查。"""
        with self._lock:
            self.total_checks += 1
            if blocked:
                self.blocked_requests += 1
                if risk_type:
                    key = risk_type.value
                    self.risk_distribution[key] = self.risk_distribution.get(key, 0) + 1
                    if risk_type == RiskType.PROMPT_INJECTION:
                        self.prompt_injection_count += 1

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "blocked_requests": self.blocked_requests,
                "risk_distribution": dict(self.risk_distribution),
                "prompt_injection_count": self.prompt_injection_count,
                "total_checks": self.total_checks,
            }

    def reset(self) -> None:
        """重置统计。"""
        with self._lock:
            self.blocked_requests = 0
            self.risk_distribution.clear()
            self.prompt_injection_count = 0
            self.total_checks = 0


# 全局单例
security_stats = SecurityStats()

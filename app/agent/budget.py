"""ToolBudget — 工具调用预算管理器。

跟踪工具调用次数，在接近上限时发出警告，
并维护搜索历史和路径缓存以减少重复调用。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ToolBudget:
    """工具调用预算。"""

    max_calls: int = 20
    current_calls: int = 0

    # 搜索历史：记录已搜索的 query
    search_history: list[str] = field(default_factory=list)

    # 已读取的文件路径
    read_files: list[str] = field(default_factory=list)

    # 路径缓存：query → file_path
    path_cache: dict[str, str] = field(default_factory=dict)

    @property
    def remaining_calls(self) -> int:
        return max(0, self.max_calls - self.current_calls)

    def consume(self) -> None:
        """消耗一次工具调用。"""
        self.current_calls += 1

    def should_warn(self) -> bool:
        """是否应该发出预算警告（剩余 ≤3）。"""
        return self.remaining_calls <= 3

    def should_stop(self) -> bool:
        """是否应该停止（无剩余调用）。"""
        return self.remaining_calls <= 0

    def record_search(self, query: str) -> None:
        """记录搜索 query。"""
        normalized = query.strip().lower()
        if normalized not in self.search_history:
            self.search_history.append(normalized)

    def is_duplicate_search(self, query: str) -> bool:
        """检查是否为重复搜索。"""
        normalized = query.strip().lower()
        return normalized in self.search_history

    def cache_path(self, query: str, file_path: str) -> None:
        """缓存搜索结果中的文件路径。"""
        normalized = query.strip().lower()
        self.path_cache[normalized] = file_path

    def get_cached_path(self, query: str) -> str | None:
        """获取缓存的文件路径。"""
        normalized = query.strip().lower()
        return self.path_cache.get(normalized)

    def record_read(self, file_path: str) -> None:
        """记录已读取的文件路径。"""
        if file_path not in self.read_files:
            self.read_files.append(file_path)

    def has_read(self, file_path: str) -> bool:
        """检查是否已读取过该文件。"""
        return file_path in self.read_files

    def get_budget_prompt(self) -> str:
        """生成预算提示信息，注入到 system message 中。"""
        parts = []

        if self.should_stop():
            parts.append(
                "【紧急】已达到工具调用上限，无法继续执行工具。"
                "请立即基于已有信息生成最终回答。"
            )
        elif self.should_warn():
            remaining = self.remaining_calls
            parts.append(
                f"【预算警告】剩余工具调用次数: {remaining}。"
                "请停止探索，尽快完成闭环：write_file → run_tests → git_diff。"
            )
            # 动态指引：根据已有信息推荐下一步
            if self.read_files and not any(
                "write_file" in str(s) for s in self.search_history
            ):
                parts.append("你已读取文件，现在应该 write_file 完成修改。")
            elif remaining <= 1:
                parts.append("仅剩 1 次调用，请直接生成最终回答。")

        # 重复搜索警告
        if self.search_history:
            parts.append(
                f"已搜索过的主题: {', '.join(self.search_history[-5:])}。"
                "请优先利用已有结果，避免重复搜索。"
            )

        # 路径缓存提示
        if self.path_cache:
            cached_files = list(self.path_cache.values())
            parts.append(
                f"已发现的文件路径: {', '.join(cached_files)}。"
                "请直接使用 read_file 读取，无需再次搜索。"
            )

        return "\n".join(parts) if parts else ""

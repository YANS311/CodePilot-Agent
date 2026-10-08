"""Value objects for per-call context management, not persistent memory."""

from dataclasses import asdict, dataclass, field
from typing import Any


class ContextBudgetExceeded(ValueError):
    """Mandatory instructions/task/schema cannot fit without information loss."""


class ContextProtocolError(ValueError):
    """The input transcript contains an incomplete tool exchange."""


@dataclass(frozen=True)
class ContextBudget:
    max_input_tokens: int = 32768
    reserve_output_tokens: int = 4096
    system_budget: int = 4096
    workspace_budget: int = 3072
    memory_budget: int = 3072
    skill_budget: int = 4096
    history_budget: int = 16384
    tool_observation_budget: int = 2048
    recent_message_count: int = 6

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.max_input_tokens <= self.reserve_output_tokens:
            raise ValueError("max_input_tokens must exceed reserve_output_tokens")

    @property
    def usable_input_tokens(self) -> int:
        return self.max_input_tokens - self.reserve_output_tokens


@dataclass(frozen=True)
class ContextStats:
    estimated_tokens_before: int
    estimated_tokens_after: int
    messages_before: int
    messages_after: int
    tool_outputs_compressed: int = 0
    context_sections_dropped: tuple[str, ...] = ()
    context_sections_truncated: tuple[str, ...] = ()

    @property
    def tokens_saved(self) -> int:
        return max(0, self.estimated_tokens_before - self.estimated_tokens_after)

    @property
    def compression_ratio(self) -> float:
        """Retained fraction, not the savings fraction; empty context is 1.0."""
        if not self.estimated_tokens_before:
            return 1.0
        return self.estimated_tokens_after / self.estimated_tokens_before

    @property
    def compaction_triggered(self) -> bool:
        return bool(
            self.tokens_saved or self.messages_before != self.messages_after
            or self.tool_outputs_compressed
            or self.context_sections_dropped or self.context_sections_truncated
        )

    def to_metadata(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "tokens_saved": self.tokens_saved,
            "compression_ratio": self.compression_ratio,
            "compaction_triggered": self.compaction_triggered,
        }


@dataclass
class ContextBuildResult:
    messages: list[dict[str, Any]]
    stats: ContextStats
    core_system: str | None = None
    optional_sections: dict[str, str] = field(default_factory=dict)

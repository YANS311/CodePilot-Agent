"""Explicit execution-state contract; no clients, registries or arbitrary objects."""

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agent.budget import ToolBudget
from app.agent.context import ContextBudget
from app.agent.context.compactor import group_messages
from app.agent.error_event import AgentErrorEvent
from app.agent.trace import ExecutionStepTrace, TraceEvent
from app.agent.verification import VerificationPolicy
from app.models.state import AgentState
from app.models.tool import AgentStep, ToolResult

SCHEMA_VERSION = "1.0"
TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled", "budget_exhausted", "verification_failed"})


class CheckpointError(ValueError):
    pass


class CheckpointBusy(CheckpointError):
    pass


class ResumeRejected(CheckpointError):
    def __init__(self, reason: str, trace=None):
        super().__init__(reason)
        self.trace = trace


def validate_task_id(task_id: str) -> str:
    if not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", task_id):
        raise CheckpointError("Invalid checkpoint task ID")
    return task_id


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, validate_assignment=True)


class ToolFunction(ContractModel):
    name: str = Field(min_length=1, max_length=256)
    arguments: str


class AssistantCall(ContractModel):
    id: str = Field(min_length=1, max_length=256)
    type: Literal["function"]
    function: ToolFunction


class WireMessage(ContractModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[AssistantCall] | None = None


class PendingCall(ContractModel):
    id: str = Field(min_length=1, max_length=256)
    name: str = Field(min_length=1, max_length=256)
    replay_class: Literal["read_only", "idempotent", "side_effecting"] = "side_effecting"


class ResultSnapshot(ContractModel):
    answer: str = ""
    tool_calls_count: int = Field(default=0, ge=0)
    tool_results: list[ToolResult] = Field(default_factory=list)
    thoughts: list[str] = Field(default_factory=list)
    steps: list[AgentStep] = Field(default_factory=list)
    security_warnings: list[dict[str, Any]] = Field(default_factory=list)
    wrote_file: bool = False
    no_code_change_reason: str = ""
    error_events: list[AgentErrorEvent] = Field(default_factory=list)
    verification_passed: bool = False
    verification_retries: int = Field(default=0, ge=0)
    test_result: str = ""
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0, le=1)

    @classmethod
    def capture(cls, result):
        return cls(**{name: getattr(result, name) for name in cls.model_fields})


class TraceSnapshot(ContractModel):
    events: list[TraceEvent] = Field(default_factory=list)
    steps: list[ExecutionStepTrace] = Field(default_factory=list)
    next_event_id: int = Field(default=1, ge=1)
    total_latency_ms: float = Field(default=0.0, ge=0)
    status: str = "running"
    created_at: float


class AgentCheckpoint(ContractModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    task_id: str
    task: str
    task_digest: str
    workspace_root: str
    workspace_digest: str
    status: Literal[
        "created", "running", "checkpointed", "resumed", "indeterminate",
        "completed", "failed", "cancelled", "budget_exhausted", "verification_failed",
    ] = "created"
    next_step: Literal["initializing", "core", "repair", "verify", "summary", "finish", "terminal"] = "initializing"
    runtime: AgentState
    messages: list[dict[str, Any]] = Field(default_factory=list)
    active_skill: str | None = None
    budget: ToolBudget
    drift_corrected: bool = False
    completion_corrected: bool = False
    completed_tool_ids: list[str] = Field(default_factory=list)
    last_completed_outcome: ToolResult | None = None
    in_flight: list[PendingCall] = Field(default_factory=list)
    verification: VerificationPolicy
    verification_attempt: int = Field(default=0, ge=0)
    context_budget: ContextBudget
    core_system: str | None = None
    optional_sections: dict[str, str] = Field(default_factory=dict)
    estimator_name: str
    tools_digest: str
    result: ResultSnapshot = Field(default_factory=ResultSnapshot)
    trace: TraceSnapshot
    guardrail_read_count: int = Field(default=0, ge=0)
    guardrail_read_timestamps: list[float] = Field(default_factory=list)
    memory_attempted: bool = False
    resume_count: int = Field(default=0, ge=0)
    revision: int = Field(default=0, ge=0)
    created_at: str = Field(default_factory=timestamp)
    updated_at: str = Field(default_factory=timestamp)

    @model_validator(mode="after")
    def validate_contract(self):
        validate_task_id(self.task_id)
        if self.task_digest != digest(self.task):
            raise ValueError("Task identity mismatch")
        if self.runtime.task_id != self.task_id or self.runtime.workspace_path != self.workspace_root:
            raise ValueError("Runtime identity mismatch")
        if not 0 <= self.runtime.iteration <= self.runtime.max_iterations or self.runtime.max_iterations != self.budget.max_calls:
            raise ValueError("Invalid iteration state")
        if not 0 <= self.budget.current_calls <= self.budget.max_calls or self.budget.max_calls < 1:
            raise ValueError("Invalid consumed tool budget")
        if self.verification.max_retries < 0 or self.verification_attempt > self.verification.max_retries:
            raise ValueError("Invalid verification state")
        if set(self.optional_sections) - {"workspace", "memory", "skill"}:
            raise ValueError("Unknown context section")
        for message in self.messages:
            WireMessage.model_validate(message)
        group_messages(self.messages)
        users = [message for message in self.messages if message["role"] == "user"]
        if self.next_step != "initializing" and (not users or users[0]["content"] != self.task):
            raise ValueError("Checkpoint does not preserve current task")
        if self.core_system is not None:
            expected = self.core_system + "\n\n" + "".join(self.optional_sections.get(n, "") for n in ("workspace", "memory", "skill"))
            if not self.messages or self.messages[0] != {"role": "system", "content": expected}:
                raise ValueError("Context section boundaries do not match messages")
        ids = [result.tool_call_id for result in self.result.tool_results]
        if len(set(ids)) != len(ids) or set(ids) != set(self.completed_tool_ids) or len(set(self.completed_tool_ids)) != len(self.completed_tool_ids):
            raise ValueError("Completed tool identity mismatch")
        if self.result.tool_calls_count != len(ids):
            raise ValueError("Tool outcome count mismatch")
        if self.last_completed_outcome is not None and self.last_completed_outcome.tool_call_id not in self.completed_tool_ids:
            raise ValueError("Last tool outcome is not completed")
        pending = [call.id for call in self.in_flight]
        if len(set(pending)) != len(pending) or set(pending).intersection(ids):
            raise ValueError("Invalid in-flight call identities")
        if bool(self.in_flight) != (self.status == "indeterminate"):
            raise ValueError("In-flight calls require indeterminate status")
        previous = 0
        for event in self.trace.events:
            if event.task_id != self.task_id or event.step_id <= previous or event.schema_version != "0.1":
                raise ValueError("Invalid checkpoint trace ownership/order/version")
            previous = event.step_id
        if self.trace.next_event_id <= previous:
            raise ValueError("Trace cursor must exceed saved events")
        for value in (self.created_at, self.updated_at):
            if datetime.fromisoformat(value).tzinfo is None:
                raise ValueError("Checkpoint timestamps require timezone")
        return self

import json
from types import SimpleNamespace

import pytest
from pydantic_core import PydanticSerializationError

from app.agent.checkpoint import CheckpointBusy, CheckpointError, CheckpointManager, FileCheckpointStore
from app.agent.checkpoint.manager import _linked_entry
from app.agent.context import ContextManager
from app.agent.trace import ExecutionTrace
from app.agent.verification import VerificationPolicy


@pytest.fixture
def setup(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "source.py").write_text("print('hello')", encoding="utf-8")
    store = FileCheckpointStore(tmp_path / "private-checkpoints")
    manager = CheckpointManager(store)
    context = ContextManager()
    trace = ExecutionTrace(task="Inspect source", task_id="task-1")
    trace.record_event("task_start")
    state = manager.create("task-1", "Inspect source", str(workspace), 8, VerificationPolicy.disabled(), context, [], trace)
    initial = context.build_initial_context(system="SAFETY", task=state.task)
    state = state.model_copy(update={
        "status": "checkpointed", "next_step": "core", "messages": initial.messages,
        "core_system": initial.core_system, "optional_sections": initial.optional_sections,
    })
    return workspace, store, manager, state, context, trace


def test_json_round_trip_and_new_store_instance(setup):
    workspace, store, manager, state, _, _ = setup
    saved = store.save(state)
    loaded = FileCheckpointStore(store.root).load(state.task_id)
    assert loaded == saved
    assert saved.schema_version == "1.0"
    assert saved.revision == 1
    assert loaded.budget.remaining_calls == 8
    assert store.list_tasks() == ["task-1"]
    store.delete("task-1")
    assert store.list_tasks() == []


@pytest.mark.parametrize("task_id", ["../x", "..\\x", "a/b", "C:\\x", "", ".", "x.json", "x" * 65])
def test_invalid_ids_never_form_paths(tmp_path, task_id):
    store = FileCheckpointStore(tmp_path / "store")
    with pytest.raises(CheckpointError, match="task ID"):
        store.load(task_id)
    with pytest.raises(CheckpointError):
        store.delete(task_id)


@pytest.mark.parametrize("raw", ['{"schema_version": "999"}', '{broken', '[]'])
def test_corrupted_or_unsupported_json_rejected(setup, raw):
    _, store, _, _, _, _ = setup
    (store.root / "cp-task-1.json").write_text(raw, encoding="utf-8")
    with pytest.raises(CheckpointError):
        store.load("task-1")


def test_version_validation_on_complete_snapshot(setup):
    _, store, _, state, _, _ = setup
    data = state.model_dump(mode="json")
    data["schema_version"] = "2.0"
    (store.root / "cp-task-1.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(CheckpointError):
        store.load("task-1")


def test_atomic_failure_keeps_previous_snapshot_and_cleans_temp(setup, monkeypatch):
    _, store, _, state, _, _ = setup
    old = store.save(state)
    updated = old.model_copy(update={"resume_count": 1})

    def fail_replace(*args):
        raise OSError("simulated atomic replacement failure")

    monkeypatch.setattr("app.agent.checkpoint.store.os.replace", fail_replace)
    with pytest.raises(OSError):
        store.save(updated)
    assert store.load(state.task_id) == old
    assert list(store.root.glob("*.tmp")) == []


def test_save_fsyncs_before_atomic_replace(setup, monkeypatch):
    _, store, _, state, _, _ = setup
    import os
    fsync, replace = os.fsync, os.replace
    calls = []

    def synced(fd):
        calls.append("fsync")
        fsync(fd)

    def replaced(source, target):
        calls.append("replace")
        replace(source, target)

    monkeypatch.setattr("app.agent.checkpoint.store.os.fsync", synced)
    monkeypatch.setattr("app.agent.checkpoint.store.os.replace", replaced)
    store.save(state)
    assert calls.index("fsync") < calls.index("replace")


def test_stale_revision_and_competing_lease_rejected(setup):
    _, store, _, state, _, _ = setup
    first = store.save(state)
    store.save(first)
    with pytest.raises(CheckpointError, match="Stale"):
        store.save(first)
    other = FileCheckpointStore(store.root)
    with store.lease(state.task_id):
        with pytest.raises(CheckpointBusy):
            with other.lease(state.task_id):
                pytest.fail("must never claim a running task")
        with pytest.raises(CheckpointBusy):
            other.delete(state.task_id)
    with other.lease(state.task_id):
        pass


def test_size_limit_rejects_save_and_load(setup):
    _, store, _, state, _, _ = setup
    tiny = FileCheckpointStore(store.root, max_size_bytes=10)
    with pytest.raises(CheckpointError, match="size limit"):
        tiny.save(state)
    store.save(state)
    with pytest.raises(CheckpointError, match="size limit"):
        tiny.load(state.task_id)


@pytest.mark.parametrize("text", ["Authorization: Bearer abcdefghijk", "api_key=abcdefghijk", "sk-abcdefghijklmnop", "-----BEGIN PRIVATE KEY-----"])
def test_credentials_are_rejected_without_persisting(setup, text):
    _, store, _, state, _, _ = setup
    unsafe = state.model_copy(update={"messages": state.messages + [{"role": "assistant", "content": text}]})
    with pytest.raises(CheckpointError, match="credential"):
        store.save(unsafe)
    assert not list(store.root.glob("cp-*.json"))


def test_known_secret_value_and_arbitrary_objects_are_not_serialized(setup):
    _, store, _, state, _, _ = setup
    store.forbidden_values = ("confidential_value",)
    unsafe = state.model_copy(update={"messages": state.messages + [{"role": "assistant", "content": "confidential_value"}]})
    with pytest.raises(CheckpointError):
        store.save(unsafe)
    with pytest.raises(PydanticSerializationError):
        store.save(state.model_copy(update={"messages": [{"role": "system", "content": object()}]}))
    assert not list(store.root.glob("cp-*.json"))


def test_invalid_protocol_identity_and_budget_rejected(setup):
    _, store, _, state, _, _ = setup
    for update in (
        {"messages": state.messages + [{"role": "tool", "tool_call_id": "missing", "content": "x"}]},
        {"task_digest": "invalid"},
        {"completed_tool_ids": ["missing"]},
        {"status": "indeterminate"},
    ):
        with pytest.raises(ValueError):
            store.save(state.model_copy(update=update))


def test_workspace_and_policy_mismatches(setup):
    workspace, _, manager, state, context, _ = setup
    validate = lambda: manager.validate_resume(state, str(workspace), 8, VerificationPolicy.disabled(), context, [])
    assert validate() is None
    (workspace / "source.py").write_text("changed", encoding="utf-8")
    assert validate() == "workspace_identity_mismatch"
    with pytest.raises(CheckpointError, match="disjoint"):
        CheckpointManager(FileCheckpointStore(workspace / "checkpoints")).validate_storage_boundary(str(workspace))


def test_indeterminate_read_and_write_both_require_recovery(setup):
    workspace, _, manager, state, context, _ = setup
    calls = manager.pending_calls([SimpleNamespace(id="read", name="read_file"), SimpleNamespace(id="write", name="write_file")])
    assert [call.replay_class for call in calls] == ["read_only", "side_effecting"]
    unsafe = state.model_copy(update={"status": "indeterminate", "in_flight": calls})
    assert manager.validate_resume(unsafe, str(workspace), 8, VerificationPolicy.disabled(), context, []) == "indeterminate_tool_exchange"


def test_trace_cursor_restoration_and_validation(setup):
    _, store, _, state, _, trace = setup
    trace.restore_cursor(20)
    assert trace.record_event("task_resumed").step_id == 20
    with pytest.raises(ValueError):
        trace.restore_cursor(1)
    invalid = state.model_copy(update={"trace": state.trace.model_copy(update={"next_event_id": 1})})
    with pytest.raises(ValueError):
        store.save(invalid)


def test_terminal_snapshot_only_allows_append_only_rejection_trace(setup):
    _, store, manager, state, _, trace = setup
    saved = store.save(state.model_copy(update={"status": "completed", "next_step": "terminal"}))
    with pytest.raises(CheckpointError, match="Terminal checkpoint"):
        store.save(saved.model_copy(update={"resume_count": 1}))
    with pytest.raises(CheckpointError, match="trace facts"):
        store.save(saved.model_copy(update={"trace": saved.trace.model_copy(update={"status": "running-again"})}))
    trace.restore_cursor(saved.trace.next_event_id)
    trace.record_event("checkpoint_loaded")
    trace.record_event("resume_rejected")
    extended = store.save(saved.model_copy(update={"trace": manager.capture_trace(trace, reserve=0)}))
    assert extended.result == saved.result
    assert len(extended.trace.events) == len(saved.trace.events) + 2


def test_mcp_or_shell_tools_never_gain_implicit_idempotency(setup):
    _, _, manager, _, _, _ = setup
    calls = manager.pending_calls([SimpleNamespace(id="external", name="mcp__server__write"), SimpleNamespace(id="shell", name="run_tests")])
    assert all(call.replay_class == "side_effecting" for call in calls)


def test_python311_windows_reparse_points_are_rejected():
    junction = SimpleNamespace(is_symlink=lambda: False, lstat=lambda: SimpleNamespace(st_file_attributes=0x400))
    regular = SimpleNamespace(is_symlink=lambda: False, lstat=lambda: SimpleNamespace(st_file_attributes=0))
    assert _linked_entry(junction)
    assert not _linked_entry(regular)

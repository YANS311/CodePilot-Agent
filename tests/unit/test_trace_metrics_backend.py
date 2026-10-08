from http.client import IncompleteRead
from io import BytesIO
import json
from unittest.mock import Mock

import pytest

from app.agent.trace import TraceEvent
from app.evaluation.harness_metrics import task_metrics
from app.evaluation.schema import EvalResult
from app.evaluation import trace_metrics_backend as backend


@pytest.fixture
def result():
    return EvalResult(task_id="t", success=True, trace_events=[
        TraceEvent("t", 1, "llm_request", metadata={"estimated_input_tokens": 12, "prompt": "secret"}),
        TraceEvent("t", 2, "tool_call", tool_name="run_tests", tool_input={"secret": "value"},
                   tool_output="sensitive", execution_result="success", metadata={"phase": "verification"}),
        TraceEvent("t", 3, "task_complete", execution_result="completed"),
    ])


def mock_remote(monkeypatch, data, status=200):
    response = BytesIO(data)
    response.status = status
    opener = Mock()
    opener.open.return_value = response
    factory = Mock(return_value=opener)
    monkeypatch.setattr(backend, "build_opener", factory)
    return opener, factory


def test_default_never_contacts_go(monkeypatch, result):
    monkeypatch.delenv("CODEPILOT_TRACE_METRICS_BACKEND", raising=False)
    opener, _ = mock_remote(monkeypatch, b"")
    measured = task_metrics(result)
    assert measured["executed_tool_calls"] == measured["verification_attempts"] == 1
    opener.open.assert_not_called()


def test_go_adapter_parity_and_projection(monkeypatch, result):
    monkeypatch.setenv("CODEPILOT_TRACE_METRICS_BACKEND", "python")
    reference = task_metrics(result)
    remote = {"task_id": "t", **{key: reference[key] for key in backend.SUMMARY_FIELDS}}
    opener, factory = mock_remote(monkeypatch, json.dumps(remote).encode())
    monkeypatch.setenv("CODEPILOT_TRACE_METRICS_BACKEND", "go")
    assert task_metrics(result) == reference
    request = opener.open.call_args.args[0]
    assert request.full_url == backend.SUMMARY_URL
    assert opener.open.call_args.kwargs == {"timeout": 0.5}
    assert b"secret" not in request.data and b"sensitive" not in request.data
    assert factory.call_args.args[0].proxies == {}


@pytest.mark.parametrize("data,status", [
    (b"invalid", 200), (b"[]", 200), (b"{}", 200), (b"null", 200),
    (b"{}", 500), (b"x" * (backend.MAX_RESPONSE_BYTES + 1), 200),
    (b'{"task_id":"other"}', 200),
])
def test_invalid_remote_preserves_python(monkeypatch, result, data, status):
    monkeypatch.setenv("CODEPILOT_TRACE_METRICS_BACKEND", "python")
    reference = task_metrics(result)
    mock_remote(monkeypatch, data, status)
    monkeypatch.setenv("CODEPILOT_TRACE_METRICS_BACKEND", "go")
    assert task_metrics(result) == reference


@pytest.mark.parametrize("change", ["wrong_task", "wrong_count", "bool_count", "extra_key"])
def test_mismatched_go_metrics_preserve_python(monkeypatch, result, change):
    monkeypatch.setenv("CODEPILOT_TRACE_METRICS_BACKEND", "python")
    reference = task_metrics(result)
    remote = {"task_id": "t", **{key: reference[key] for key in backend.SUMMARY_FIELDS}}
    if change == "wrong_task":
        remote["task_id"] = "other"
    elif change == "wrong_count":
        remote["executed_tool_calls"] = 9
    elif change == "bool_count":
        remote["executed_tool_calls"] = True
    else:
        remote["invented_metric"] = 0
    mock_remote(monkeypatch, json.dumps(remote).encode())
    monkeypatch.setenv("CODEPILOT_TRACE_METRICS_BACKEND", "go")
    assert task_metrics(result) == reference


@pytest.mark.parametrize("error", [OSError("unavailable"), TimeoutError(), IncompleteRead(b"partial")])
def test_unavailable_go_preserves_python(monkeypatch, result, error):
    monkeypatch.setenv("CODEPILOT_TRACE_METRICS_BACKEND", "python")
    reference = task_metrics(result)
    opener, _ = mock_remote(monkeypatch, b"")
    opener.open.side_effect = error
    monkeypatch.setenv("CODEPILOT_TRACE_METRICS_BACKEND", "go")
    assert task_metrics(result) == reference


def test_oversized_projection_stays_local(monkeypatch, result):
    monkeypatch.setenv("CODEPILOT_TRACE_METRICS_BACKEND", "go")
    result.trace_events[0].metadata["phase"] = "x" * backend.MAX_BODY_BYTES
    opener, _ = mock_remote(monkeypatch, b"")
    assert task_metrics(result)["total_estimated_input_tokens"] == 12
    opener.open.assert_not_called()


def test_go_flag_does_not_mask_invalid_trace(monkeypatch):
    monkeypatch.setenv("CODEPILOT_TRACE_METRICS_BACKEND", "go")
    opener, _ = mock_remote(monkeypatch, b"")
    with pytest.raises(ValueError, match="mismatch"):
        task_metrics(EvalResult(task_id="t", trace_events=[TraceEvent("other", 1, "task_start")]))
    opener.open.assert_not_called()

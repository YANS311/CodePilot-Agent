"""Optional read-only Go summary; Python remains authoritative on any failure."""

import json
import os
from http.client import HTTPException
from urllib.request import ProxyHandler, Request, build_opener


SUMMARY_FIELDS = (
    "executed_tool_calls", "llm_requests", "verification_attempts",
    "total_estimated_input_tokens", "terminal_status",
)
SUMMARY_URL = "http://127.0.0.1:8091/v1/trace/summary"
MAX_BODY_BYTES = 1 << 20
MAX_RESPONSE_BYTES = 16 << 10


def optional_go_summary(task_id, events, python_metrics):
    """Return a verified Go subset, or {} to preserve the Python calculation.

    This first integration deliberately computes the Python reference as well.
    Remote discrepancies cannot change evaluation results. It makes no speedup
    claim and sends neither prompts, tool inputs/outputs nor unrelated metadata.
    """
    if os.environ.get("CODEPILOT_TRACE_METRICS_BACKEND", "python") != "go":
        return {}
    try:
        payload = {
            "task_id": task_id,
            "events": [{
                "task_id": event.task_id, "step_id": event.step_id,
                "agent_action": event.agent_action, "tool_name": event.tool_name,
                "execution_result": event.execution_result,
                "metadata": {key: event.metadata[key] for key in ("phase", "estimated_input_tokens")
                             if key in event.metadata},
            } for event in events],
        }
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        if len(body) > MAX_BODY_BYTES:
            return {}
        request = Request(SUMMARY_URL, data=body, headers={"Content-Type": "application/json"})
        # Bypass environment proxies so trace projections stay on loopback.
        with build_opener(ProxyHandler({})).open(request, timeout=0.5) as response:
            if response.status != 200:
                return {}
            data = response.read(MAX_RESPONSE_BYTES + 1)
        if len(data) > MAX_RESPONSE_BYTES:
            return {}
        summary = json.loads(data)
        expected = {"task_id": task_id, **{key: python_metrics[key] for key in SUMMARY_FIELDS}}
        if not isinstance(summary, dict) or summary.keys() != expected.keys():
            return {}
        if any(type(summary[key]) is not type(value) or summary[key] != value
               for key, value in expected.items()):
            return {}
        return {key: summary[key] for key in SUMMARY_FIELDS}
    except (OSError, HTTPException, ValueError, TypeError, KeyError):
        # Do not log exceptions or payloads; they can contain sensitive data.
        return {}

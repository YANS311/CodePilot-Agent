"""Shared fixtures plus direct HTTP parity when a Go toolchain is available."""

import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time
from urllib.request import ProxyHandler, Request, build_opener

import pytest

from app.agent.trace import TraceEvent
from app.evaluation.harness_metrics import task_metrics
from app.evaluation.schema import EvalResult
from app.evaluation import trace_metrics_backend as backend
from app.evaluation.trace_metrics_backend import SUMMARY_FIELDS


SERVICE = Path(__file__).resolve().parents[2] / "services" / "trace-metrics-go"
CASES = json.loads((SERVICE / "testdata" / "parity.json").read_text(encoding="utf-8"))


def python_summary(case):
    request = case["request"]
    events = [TraceEvent(**event) for event in request["events"]]
    metrics = task_metrics(EvalResult(task_id=request["task_id"], trace_events=events))
    return {"task_id": request["task_id"], **{key: metrics[key] for key in SUMMARY_FIELDS}}


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_shared_python_reference(case, monkeypatch):
    monkeypatch.setenv("CODEPILOT_TRACE_METRICS_BACKEND", "python")
    assert python_summary(case) == case["expected"]


def test_live_go_python_parity(tmp_path, monkeypatch):
    go = os.environ.get("CODEPILOT_GO_EXECUTABLE") or shutil.which("go")
    if not go:
        pytest.skip("Go unavailable; shared Python fixture checks still run")
    monkeypatch.setenv("CODEPILOT_TRACE_METRICS_BACKEND", "python")
    executable = tmp_path / ("trace-metrics.exe" if os.name == "nt" else "trace-metrics")
    subprocess.run([go, "build", "-o", str(executable), "."], cwd=SERVICE, check=True, timeout=120)
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    process = subprocess.Popen([str(executable), "-addr", f"127.0.0.1:{port}"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    opener = build_opener(ProxyHandler({}))
    try:
        deadline = time.monotonic() + 10
        while True:
            try:
                with opener.open(url + "/health", timeout=0.5) as response:
                    assert json.load(response) == {"status": "ok"}
                break
            except OSError:
                if process.poll() is not None or time.monotonic() >= deadline:
                    pytest.fail("Go service failed to become healthy")
                time.sleep(0.05)
        for case in CASES:
            request = Request(url + "/v1/trace/summary", data=json.dumps(case["request"]).encode(),
                              headers={"Content-Type": "application/json"})
            with opener.open(request, timeout=1) as response:
                assert json.load(response) == python_summary(case) == case["expected"]
            with monkeypatch.context() as enabled:
                enabled.setenv("CODEPILOT_TRACE_METRICS_BACKEND", "go")
                enabled.setattr(backend, "SUMMARY_URL", url + "/v1/trace/summary")
                expected = case["expected"]
                events = [TraceEvent(**event) for event in case["request"]["events"]]
                assert backend.optional_go_summary(expected["task_id"], events, expected) == {
                    key: expected[key] for key in SUMMARY_FIELDS
                }
    finally:
        process.terminate()
        process.wait(timeout=10)

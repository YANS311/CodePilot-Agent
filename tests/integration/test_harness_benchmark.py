import asyncio
import csv
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.evaluation.context_stress import run_context_stress
from app.evaluation.harness_reporting import write_reports
from app.evaluation.harness_runner import HarnessConfig, provenance, run_ablations
from app.evaluation.manifest import audit_datasets
from app.evaluation.profiles import PROFILES
from app.evaluation.recovery_matrix import run_recovery_matrix
from scripts.run_harness_benchmark import dry_run_plan, main


@pytest.fixture(scope="module")
def experiments():
    simulated = asyncio.run(run_ablations(HarnessConfig(repetitions=1)))
    recovery = asyncio.run(run_recovery_matrix())
    real = {"label": "NOT RUN", "summary": {p.id: {"status": "NOT RUN", "trial_count": None, "task_success_rate": None, "pass_at_1": None} for p in PROFILES}}
    return {"provenance": provenance(HarnessConfig(), model="ScriptedLLM-v1", mode="offline"),
            "simulated": simulated, "real_model": real}, recovery


def test_all_profiles_real_tools_independent_tests_and_isolation(experiments):
    report, _ = experiments
    trials = report["simulated"]["trials"]
    assert len(trials) == 12
    assert len({t["trace_task_id"] for t in trials}) == 12
    assert len({t["workspace_instance_id"] for t in trials}) == 12
    assert len({t["seed_digest"] for t in trials}) == 1
    for profile in PROFILES:
        subset = [t for t in trials if t["profile"] == profile.id]
        assert all(t["memory_retrieval_calls"] == int(profile.memory) for t in subset)
        assert all(t["memory_context_hits"] == int(profile.memory) for t in subset)
        assert all(t["verification_attempts"] == 0 for t in subset) if not profile.verification else True
    assert report["simulated"]["summary"]["C"]["task_success_rate"] == 1 / 3
    assert report["simulated"]["summary"]["D"]["task_success_rate"] == 2 / 3
    recovered = next(t for t in trials if t["profile"] == "D" and t["task_id"] == "recoverable")
    assert recovered["verification_attempts"] == 2 and recovered["verification_retries"] == 1
    assert recovered["files_modified"] == ["arithmetic.py"]
    unrecovered = next(t for t in trials if t["profile"] == "D" and t["task_id"] == "unrecoverable")
    assert not unrecovered["success"] and unrecovered["terminal_status"] == "verification_failed"
    assert all(t["provider_input_tokens"] is None for t in trials)


def test_recovery_faults_are_separate_and_all_pass(experiments):
    _, matrix = experiments
    assert len(matrix["rows"]) == 6
    assert all(r["status"] == "PASS" and all(r["assertions"].values()) for r in matrix["rows"])
    write = next(r for r in matrix["rows"] if r["scenario"] == "indeterminate_write")
    assert write["executed_call_ids"] == ["write-1"]
    verify = next(r for r in matrix["rows"] if r["scenario"] == "verification_progress")
    assert verify["executed_call_ids"] == ["write-1", "verify_0", "write-2", "verify_1"]


def test_json_csv_and_markdown_consistency_and_unrun_labels(experiments, tmp_path):
    report, matrix = experiments
    write_reports(tmp_path, report, run_context_stress(), matrix, audit_datasets(), tmp_path / "report.md")
    saved = json.loads((tmp_path / "harness_ablation.json").read_text(encoding="utf-8"))
    with (tmp_path / "harness_ablation.csv").open(encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 8
    for row in rows:
        summary = saved[row["experiment"]]["summary"][row["profile"]]
        if row["status"] == "NOT RUN":
            assert row["task_success_rate"] == "" and row["pass_at_1"] == ""
        else:
            assert float(row["task_success_rate"]) == summary["task_success_rate"]
            assert float(row["avg_total_estimated_input_tokens"]) == summary["avg_total_estimated_input_tokens"]
    text = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "**SIMULATED**" in text and "NOT RUN" in text
    assert "not provider billing tokens" in text


def test_dry_run_has_cost_uncertainty_without_credentials():
    plan = dry_run_plan([SimpleNamespace(task_id="fix-subtract")], HarnessConfig(repetitions=2),
                        SimpleNamespace(llm_model="configured-model", llm_api_key="never print this credential", llm_max_retries=2))
    assert plan["trials"] == 8 and plan["estimated_cost"] is None
    assert plan["logical_llm_request_upper_estimate"] == 144
    assert "never print" not in json.dumps(plan)


def test_live_execution_without_explicit_approval_refused(tmp_path, monkeypatch):
    # Use an existing audited manifest; no LLM constructor or expensive run allowed.
    from app.evaluation.manifest import ROOT
    path = ROOT / "benchmarks/manifest.json"
    if not path.exists():
        monkeypatch.setattr("scripts.run_harness_benchmark.load_manifest", lambda p: [SimpleNamespace(task_id="fix-subtract", test_target="test_x", target_exists=True)])
    monkeypatch.setattr("app.core.llm_client.LLMClient", lambda *args: pytest.fail("must not construct a paid client"))
    with pytest.raises(SystemExit) as error:
        main(["--live", "--tasks", "fix-subtract", "--output", str(tmp_path)])
    assert error.value.code == 2
    assert not list(tmp_path.iterdir())


def test_cold_start_does_not_claim_history_effect():
    experiment = asyncio.run(run_ablations(HarnessConfig(memory_state="cold"), entries=None))
    assert all(t["memory_context_hits"] == 0 for t in experiment["trials"])

"""JSON/CSV/Markdown share measured rows and explicit NOT RUN cells."""

import csv
import json
from pathlib import Path

from app.evaluation.profiles import PROFILES


def summary_rows(report):
    rows = []
    for kind in ("real_model", "simulated"):
        for profile in PROFILES:
            values = report[kind]["summary"][profile.id]
            rows.append({"experiment": kind, "profile": profile.id, **values})
    return rows


def format_cell(value):
    if value is None:
        return "NOT RUN / N/A"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def markdown_report(report, context, recovery, manifest):
    lines = ["# Harness Benchmark Release Report", "",
             "Generated from committed machine-readable artifacts. Scripted-model results are **SIMULATED**, not real Agent/model task performance.",
             "", "## Provenance", "", "```json", json.dumps(report["provenance"], ensure_ascii=False, indent=2), "```", "",
             "Latency includes the Agent, independent final pytest and workspace cleanup; excludes seed preparation and Memory seeding. It is environment-dependent wall time, not an isolated causal overhead estimate.",
             "", "## Dataset Audit", "", "| Source | Tasks |", "|---|---:|"]
    lines.extend(f"| {source} | {count} |" for source, count in manifest["counts_by_source"].items())
    lines.extend(["", f"Missing structural test targets: {manifest['missing_test_targets'] or 'none'}.",
                  "Collection outcomes are in `benchmarks/manifest.json`; collection checks executability, not full prose-criterion coverage.",
                  "The 15 repository tasks are authored seeded fixtures across three small repositories, not external production repositories. Existing task descriptions/hints are not a clean hidden-test benchmark; difficulty is unchanged.",
                  "", "## Profiles", "", "Cumulative profiles, not independent factorial effects. Skills, core tools, schemas, runtime guardrails, permissions, generation settings, tasks and budgets are held constant.",
                  "", "| Profile | Historical Memory | Context | Automatic Verification |", "|---|---|---|---|"])
    lines.extend(f"| {p.id}: {p.name} | {p.memory} | {'budgeted compaction' if p.context else 'pass-through with same hard ceiling'} | {p.verification} |" for p in PROFILES)
    lines.extend(["", "Memory is cold or seeded explicitly per trial. The permitted seed is general arithmetic debugging procedure, not a held-out patch or test solution. Retrieval uses existing structured Memory plus fixed hash vectors, not learned semantic embeddings. No global task Memory is used.",
                  "Checkpoint is off in these profiles and only enabled in separate recovery trials. No paid benchmarking was started automatically."])
    for kind, title in (("real_model", "Real Model Task Performance"), ("simulated", "Simulated Runtime Regression")):
        lines.extend(["", f"## {title}", "", "| Profile | Status | Trials | Fixture success / TSR | Tools mean | LLM requests mean | Total estimated input tokens mean | Latency ms mean |", "|---|---|---:|---:|---:|---:|---:|---:|"])
        for profile in PROFILES:
            s = report[kind]["summary"][profile.id]
            values = [profile.id, s["status"], s["trial_count"], s.get("task_success_rate"), s.get("avg_executed_tool_calls"),
                      s.get("avg_llm_requests"), s.get("avg_total_estimated_input_tokens"), s.get("avg_task_latency_ms")]
            lines.append("| " + " | ".join(format_cell(v) for v in values) + " |")
    lines.extend(["", "Real-model Memory/context/verification effectiveness is **NOT RUN** unless the real-model section contains authorized measured trials. Simulated fixtures do not establish model improvement. Pass@1 is N/A: this protocol has iterative edits/recovery, not independent one-candidate sampling.",
                  "", "## Verification Comparison (SIMULATED)", "", "Independent identical pytest is the success criterion for every profile. The scripted client deliberately exercises correct-first-edit, failed-then-repair, and unrecoverable branches.",
                  "", "| Profile | Task | Independent success | Automatic test attempts | Recovered failure | Verification tool latency ms |", "|---|---|---|---:|---|---:|"])
    for row in report["simulated"]["trials"]:
        if row["profile"] in {"C", "D"}:
            lines.append(f"| {row['profile']} | {row['task_id']} (rep {row['repetition']}) | {row['success']} | {row['verification_attempts']} | {row['recovered_test_failure']} | {row['verification_latency_ms']:.3f} |")
    lines.extend(["", "Verification adds tool/model calls and wall time. The first-pass fixture needs no repair; the unrecoverable fixture remains incorrect despite extra verification. Recovery of the scripted repair fixture is contract evidence, not a measured LLM success gain.",
                  "", "## Deterministic Context Stress", "", "| Scenario | Compaction | Status | Before estimates | After estimates | Retained ratio | Head / tail evidence | Protocol |", "|---|---|---|---:|---:|---:|---|---|"])
    for row in context["rows"]:
        lines.append("| " + " | ".join(format_cell(v) for v in [row["scenario"], row["compaction"], row["status"], row["before_estimated_input_tokens"], row["after_estimated_input_tokens"], row["retained_ratio"], f"{row['evidence_head_retained']} / {row['evidence_tail_retained']}", row["protocol_valid"]]) + " |")
    lines.extend(["", "These are UTF-8 bytes/3 input estimates, not provider billing tokens. Local tokens saved by compaction are not summed hypothetical billing savings; total task estimates sum actual logical LLM invocations. A shorter prompt can lead to more requests. Provider usage, when supplied, is separate in trial JSON; client HTTP retries are not counted as new logical requests. Head/tail sentinels measure specific retained evidence, not semantic sufficiency for a model.",
                  "", "## Checkpoint Fault Injection", "", "| Scenario | Outcome | Assertions |", "|---|---|---|"])
    for row in recovery["rows"]:
        lines.append(f"| {row['scenario']} | {row['status']} | {json.dumps(row['assertions'], sort_keys=True)} |")
    lines.extend(["", "Real file/test tools with scripted LLMs and new runtime objects; safe resumes preserve budget/context, uncertain writes refuse replay, completed verification is not repeated, changed workspaces/corrupt state/policy mismatch reject. Reliability is separate from normal TSR. No exactly-once guarantee.",
                  "", "## Reproduce", "", "```bash", "python scripts/run_harness_benchmark.py --offline --repetitions 2", "python scripts/run_harness_benchmark.py --dry-run --tasks fix-subtract --repetitions 2", "```", "",
                  "Live execution requires explicit `--live --approve-paid` after inspecting the dry-run plan and provider configuration. This release has not authorized or run it.",
                  "", "## Release Decision And Limits", "", "Freeze the job-application release after this PR. No next feature milestone is scheduled.",
                  "Single-host recovery, heuristic injection checks, bounded deterministic context, trusted test/MCP executors and non-transactional Memory publication remain limitations. Local subprocesses are not a multi-tenant security sandbox; arbitrary executors need OS/container isolation. No production rollout, business impact, billing reduction or general model improvement is claimed.", ""])
    return "\n".join(lines)


def write_reports(output, report, context, recovery, manifest, markdown_path):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    for name, value in (("harness_ablation.json", report), ("context_stress.json", context), ("recovery_matrix.json", recovery)):
        (output / name).write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n", encoding="utf-8")
    rows = summary_rows(report)
    fields = sorted({key for row in rows for key in row})
    with (output / "harness_ablation.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else value for key, value in row.items()})
    Path(markdown_path).parent.mkdir(parents=True, exist_ok=True)
    Path(markdown_path).write_text(markdown_report(report, context, recovery, manifest), encoding="utf-8")

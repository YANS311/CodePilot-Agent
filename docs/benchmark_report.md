# CodePilot Agent Benchmark Report

**Generated**: 2026-07-04 16:27:07
**Baselines**: not_available

## Overall Comparison

| Baseline | Layer | Tasks | Passed | Failed | TSR | Pass@1 | Avg Tools | Verification Rate | Edit Precision |
|----------|-------|------:|-------:|-------:|----:|-------:|----------:|------------------:|---------------:|
| not_available | all | 30 | 27 | 3 | 90.0% | 90.0% | 7.0 | not_available | not_available |

## Layer Breakdown

### not_available

not_available

## Agent-Specific Metrics

| Baseline | Verification Rate | Edit Precision | Avg Tool Calls | Tool Calls/Success |
|----------|------------------:|---------------:|---------------:|-------------------:|
| not_available | not_available | not_available | 7.0 | 6.9 |

## Difficulty Breakdown

### not_available

| Difficulty | Total | Passed | Pass Rate |
|------------|------:|-------:|----------:|
| easy | 10 | 10 | 100.0% |
| medium | 12 | 11 | 91.7% |
| hard | 8 | 6 | 75.0% |

## Reproducing

```bash
# From existing JSON reports (no eval run needed)
python scripts/generate_benchmark_report.py \
  --baseline-files reports/react_full.json reports/bare_llm.json \
  --output-md docs/benchmark_report.md

# From single report
python scripts/generate_benchmark_report.py \
  --from-json reports/eval_report.json \
  --output-md docs/benchmark_report.md
```

## Known Limitations

- Missing fields are reported as `not_available` rather than fabricated.
- CI/mock reports are not real model performance.
- `bare_llm` is a conservative text-only baseline (no tools, no agent loop).
- Metrics depend on trace availability from the evaluation runner.
- `retry_recovery_rate` is not yet tracked and shows `not_available`.

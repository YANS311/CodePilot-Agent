# Real-World Repo Bug Benchmark

15 bug-fixing tasks across 3 small Python repos with seeded bugs.

## Repos

| Repo | Files | Bugs | Tests |
|------|-------|------|-------|
| `todo_api` | FastAPI todo CRUD | 3 bugs (persistence, filter, return value) | 4 failing / 5 passing |
| `calculator_pkg` | Math operations | 4 bugs (operator, zero-div, off-by-one, sign) | 4 failing / 22 passing |
| `config_parser` | JSON config loader | 5 bugs (missing file, parse error, dead code, type check, iteration) | 7 failing / 7 passing |

## Task Distribution

- **Easy (6)**: Single-bug fixes in todo_api and calculator_pkg
- **Medium (6)**: Single-bug fixes in calculator_pkg and config_parser
- **Hard (3)**: Multi-bug fixes across entire repos

## Quick Start

```bash
# Dry run — verify bugs exist
py scripts/run_realworld_eval.py --dry-run

# Run all tasks
py scripts/run_realworld_eval.py

# Run specific tasks
py scripts/run_realworld_eval.py --tasks todo-01,calc-01

# Verify infrastructure
py -m pytest tests/test_realworld_benchmark.py -v
```

## Output

Reports go to `benchmarks/real_world/reports/`:
- `eval_TIMESTAMP.json` — machine-readable results
- `eval_TIMESTAMP.md` — human-readable report

## Metrics

- **Fix Rate**: % of tasks where all tests pass after agent fix
- **By Difficulty**: fix rate split by easy/medium/hard
- **By Repo**: fix rate split by repo
- **Modified Files Accuracy**: did the agent touch the right files?

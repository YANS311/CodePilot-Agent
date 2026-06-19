# Evaluation Report

**Generated**: 2026-06-18 | **Tasks**: 30 | **Agent**: GPT-4o

## Summary

| Metric | Value |
|--------|-------|
| **Task Success Rate (TSR)** | **90.0%** (27/30) |
| Pass@1 | 90.0% |
| Test Pass Rate | 96.6% (85/88) |
| Tool Efficiency | 0.117 |
| Avg Tool Calls/Success | 8.6 |
| Avg Duration/Task | ~55s |

## Results by Difficulty

| Difficulty | Tasks | Passed | Rate |
|:-----------|------:|-------:|-----:|
| Easy       |    10 |     10 | **100%** |
| Medium     |    12 |     11 | **92%** |
| Hard       |     8 |      6 | **75%** |

## Error Distribution

| Error Type | Count | Description |
|:-----------|------:|:------------|
| `test_not_executed` | 2 | Agent modified code but did not run tests to verify |
| `no_code_change` | 1 | Agent claimed to fix the bug but did not call `write_file` |

See [error-taxonomy.md](error-taxonomy.md) for the full 7-type taxonomy.

## All Tasks

### Easy (10/10)

| ID | Task | Tools | Duration |
|:---|:-----|------:|---------:|
| fix-subtract | Fix `subtract` arithmetic error | 7 | 27s |
| fix-reverse-string | Fix `reverse_string` off-by-one | 7 | 24s |
| fix-count-vowels | Fix `count_vowels` off-by-one | 7 | 25s |
| fix-todo-list-pending | Fix `list_pending` condition inversion | 7 | 31s |
| fix-user-to-dict | Fix `User.to_dict` missing `created_at` | 7 | 31s |
| fix-task-to-dict | Fix `Task.to_dict` missing `priority` | 9 | 51s |
| fix-import | Fix broken import statement | 8 | 31s |
| fix-count-words | Fix `count_words` empty line handling | 9 | 66s |
| fix-capitalize-tabs | Fix `capitalize_words` space-only split | 8 | 41s |
| fix-todo-complete | Fix `complete` not calling `_save()` | 7 | 35s |

### Medium (11/12)

| ID | Task | Tools | Duration | Status |
|:---|:-----|------:|---------:|:-------|
| fix-divide-zero | Add divide-by-zero check | 8 | 60s | PASS |
| fix-factorial | Fix `factorial` off-by-one | 8 | 46s | PASS |
| fix-merge-configs | Fix `merge_configs` no deep merge | 7 | 27s | PASS |
| fix-get-config-value | Fix `get_config_value` default value | 9 | 100s | PASS |
| fix-replace-in-file | Fix `replace_in_file` same old/new | 11 | 68s | PASS |
| fix-build-url | Fix `build_url` no URL encoding | 7 | 29s | PASS |
| fix-parse-response | Fix `parse_response` missing status | 7 | 30s | PASS |
| fix-list-by-priority | Fix `list_by_priority` returns None | 9 | 41s | PASS |
| fix-find-longest-line | Fix `find_longest_line` multi-line tie | 9 | 155s | PASS |
| add-validation | Add type validation to Calculator | 8 | 34s | PASS |
| fix-user-deactivate | Fix `deactivate` no timestamp | 12 | 60s | PASS |
| **fix-append-line** | Fix `append_line` double newline | 7 | 92s | **FAIL** |

### Hard (6/8)

| ID | Task | Tools | Duration | Status |
|:---|:-----|------:|---------:|:-------|
| fix-retry-request | Fix `retry_request` no delay | 7 | 47s | **FAIL** |
| fix-multi-file-todo | Fix TodoService 2 bugs | 8 | 30s | PASS |
| fix-config-all | Fix config_parser 3 bugs | 10 | 131s | PASS |
| fix-data-models-all | Fix data_models 3 bugs | 13 | 49s | PASS |
| fix-file-processor-all | Fix file_processor 3 bugs | 8 | 112s | **FAIL** |
| fix-string-utils-all | Fix string_utils 4 bugs | 13 | 108s | PASS |
| fix-api-client-all | Fix api_client 3 bugs | 8 | 52s | PASS |
| fix-all-calculator | Fix buggy_calculator 4 bugs | 8 | 38s | PASS |

## Failed Task Analysis

### fix-append-line (Medium)
- **Error**: `test_not_executed`
- **Root cause**: Agent modified the file but did not run `run_tests` to verify the fix

### fix-retry-request (Hard)
- **Error**: `no_code_change`
- **Root cause**: Agent described the fix in text but did not actually call `write_file`

### fix-file-processor-all (Hard)
- **Error**: `test_not_executed`
- **Root cause**: Agent fixed some bugs but did not run tests to check all 3 fixes

## Reproducing

```bash
# Full evaluation
python scripts/run_eval.py

# Single task
python scripts/run_eval.py --tasks fix-subtract

# Output
# - reports/eval_report.json (machine-readable)
# - reports/eval_report.md   (human-readable)
```

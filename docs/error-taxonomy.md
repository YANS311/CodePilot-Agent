# Error Taxonomy

CodePilot classifies agent failures into 7 error types. When a task fails, `analyze_error()` automatically determines the root cause based on tool call history and output patterns.

## Error Types

| # | Error Type | Code | Description |
|---|-----------|------|-------------|
| 1 | Tool Call Format Drift | `tool_call_format_drift` | Model wrote tool calls as text instead of using Function Calling protocol |
| 2 | Path Resolution Error | `path_resolution_error` | Agent referenced wrong file path |
| 3 | Test Not Executed | `test_not_executed` | Agent modified code but did not run tests |
| 4 | Test Failed | `test_failed` | Tests were executed but failed |
| 5 | Max Tool Calls Exceeded | `max_tool_calls_exceeded` | Reached the tool call limit (default: 20) |
| 6 | No Code Change | `no_code_change` | Agent claimed to fix the bug but did not call `write_file` |
| 7 | Diff Unavailable | `diff_unavailable` | `git diff` failed (workspace not a git repo) |

## Detection Logic

Errors are detected in priority order (first match wins):

```
1. tool_calls_count >= max
   └─ final_answer contains fake tool call patterns? → TOOL_CALL_FORMAT_DRIFT
   └─ else → MAX_TOOL_CALLS_EXCEEDED

2. No write_file call in tool history
   └─ Agent claims to have fixed? → NO_CODE_CHANGE

3. No run_tests call in tool history
   └─ Tests not passed? → TEST_NOT_EXECUTED

4. Tests executed but failed
   └─ TEST_FAILED

5. Fallback → UNKNOWN
```

## Tool Call Format Drift

The most interesting failure mode. Some LLMs (especially smaller or fine-tuned models) write tool calls as natural language:

```
I'll fix the bug now.

write_file("examples/calculator.py", """
def subtract(a, b):
    return a - b
""")
```

Instead of using the proper Function Calling protocol:

```json
{
  "tool_calls": [{
    "function": {
      "name": "write_file",
      "arguments": "{\"path\": \"examples/calculator.py\", \"content\": \"...\"}"
    }
  }]
}
```

### Guardrail

The agent uses three layers of defense:

1. **Prompt rules** — System prompt explicitly forbids text-based tool calls
2. **Regex detection** — Post-processing scans `final_answer` for fake patterns
3. **Correction injection** — If detected, a system message is injected reminding the model to use proper tool calls

```python
_TOOL_DRIFT_PATTERNS = [
    re.compile(r"write_file\s*\(", re.IGNORECASE),
    re.compile(r"read_file\s*\(", re.IGNORECASE),
    re.compile(r"Action:\s*write_file", re.IGNORECASE),
]
```

## Current Distribution

From the 30-task evaluation:

| Error Type | Count | % of Failures |
|:-----------|------:|---------------:|
| test_not_executed | 2 | 67% |
| no_code_change | 1 | 33% |
| **Total failures** | **3** | |

The remaining 27 tasks (90%) completed successfully.

## Adding New Error Types

To add a new error type:

1. Add to `ErrorType` enum in `app/evaluation/error_taxonomy.py`
2. Add detection logic in `app/evaluation/analyzer.py`
3. Add description in `ERROR_DESCRIPTIONS`

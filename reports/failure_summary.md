# Failure Analysis Report

**Total failed tasks**: 3 / 30 (TSR = 90%)

## Root Cause Classification

| Task | Cluster | Root Cause | Description |
|:-----|:--------|:-----------|:------------|
| fix-append-line | **file_modification** | Agent 的修复逻辑不正确 | Agent 写了两次修复，但 append_line 的行为与测试期望不匹配 |
| fix-retry-request | **test_infrastructure** | 缺少测试用例 | Agent 正确修复了代码，但没有测试可以验证（TestRetryRequest 不存在） |
| fix-file-processor-all | **planning** | 工具调用规划不当 | 花了 5 步做冗余搜索，用完 8 次工具调用限制，来不及写修复 |

## Failure Distribution

| Category | Count | % | Tasks |
|:---------|------:|--:|:------|
| planning | 1 | 33% | fix-file-processor-all |
| file_modification | 1 | 33% | fix-append-line |
| test_infrastructure | 1 | 33% | fix-retry-request |

## Detailed Analysis

### fix-append-line — File Modification Error

**Trace summary**:
1. Read file ✓
2. Wrote fix #1 (simple `rstrip`) → ran tests → 3 failed
3. Read test file to understand expectations
4. Wrote fix #2 (complex: check file end, conditionally write newline) → ran tests → still 3 failed
5. Ran out of tool calls

**Root cause**: Agent's fix logic was incorrect. The test expects `append_line(path, "second\n")` to produce `["first", "second\n"]` via `readlines()`, but the agent's implementation produced different output. The agent needed to understand the exact bytes being written, not just the high-level logic.

**Fix difficulty**: Medium — the fix requires understanding binary file I/O, not just string manipulation.

---

### fix-retry-request — Test Infrastructure Gap

**Trace summary**:
1. Read file (wrong path `workspace/examples/...` → searched → found correct path) ✓
2. Wrote correct fix (added `import time` + `time.sleep(2 ** attempt)`) ✓
3. Ran tests with wrong target `examples/` → 0 tests ran
4. Searched for retry_request tests → **none found**
5. Tried git_diff/git_status → failed (not a git repo)
6. Gave up — described fix in text

**Root cause**: The task's `test_target` is `tests/test_api_client.py::TestRetryRequest` but that test class doesn't exist in the test file. The agent correctly fixed the code but had no way to verify.

**This is a test gap, not an agent failure.** The agent's fix was correct.

---

### fix-file-processor-all — Planning Error

**Trace summary**:
1. Read file (wrong path → searched → found) 
2. Searched for `replace_in_file` → found
3. Searched for `append_line` → found
4. Searched for `find_longest_line` → found
5. Read source file ✓
6. Read test file ✓
7. Ran tests → 3 failed
8. **Out of tool calls** — never wrote any fix

**Root cause**: Agent wasted 3 tool calls on individual function searches when a single `search_code("file_processor")` would suffice. By the time it understood the problem, it had only 1 tool call left — not enough to write a fix for 3 bugs.

**Fix**: Reduce search steps, or increase max_tool_calls for hard tasks.

## Common Patterns

1. **Path resolution**: Both fix-retry-request and fix-file-processor-all failed on the first `read_file` with `workspace/examples/...` prefix. The workspace root is already set correctly, so `examples/...` is the right path.

2. **Wrong test target**: Both fix-append-line and fix-retry-request ran `run_tests` with `examples/` as target (0 tests), then had to search for the correct test file. This wastes tool calls.

3. **Tool call budget**: Hard tasks (multi-bug fixes) hit the 8-tool-call limit. The agent needs more calls or better planning for complex tasks.

## Improvement Suggestions

### Priority 1: Fix test infrastructure (fix-retry-request)
- Add `TestRetryRequest` test class to `tests/test_api_client.py`
- This is a pure test gap — fixing it should immediately recover 1 task → TSR 93.3%

### Priority 2: Improve agent planning for multi-bug tasks
- For hard tasks, consider increasing `max_tool_calls` from 8 to 12-15
- Or: teach the agent to batch operations (read once, fix all, test once)

### Priority 3: Fix path hint in task prompts
- Task prompts say `workspace/examples/...` but the agent should use `examples/...`
- Either fix the prompts or teach the agent to strip the `workspace/` prefix

## TSR Projection

| Fix | Impact | Projected TSR |
|:----|:-------|:--------------|
| Add missing test for retry_request | +1 task | 93.3% (28/30) |
| Increase max_tool_calls for hard tasks | +1 task | 96.7% (29/30) |
| Both fixes combined | +2 tasks | 96.7% (29/30) |
| Fix append_line test expectations | +1 task | 100% (30/30) |

**Most valuable single fix**: Add the missing `TestRetryRequest` test — pure test infrastructure fix, no agent changes needed, immediately recovers 1 task.

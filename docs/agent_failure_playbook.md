# Agent Failure Diagnosis Playbook

> Step-by-step diagnosis for common agent failures.
> Based on real execution traces from self-testing sessions.

---

## 1. Agent Didn't Call write_file

**Symptoms:** Agent returns analysis/answer but no file was modified.

**Diagnosis steps:**

| Step | Check | Tool |
|------|-------|------|
| 1 | Is task a code modification? | `task.lower()` contains fix/write/create/modify |
| 2 | Did agent call write_file? | `result.steps` → check `tool_name == "write_file"` |
| 3 | What is `wrote_file` metric? | `result.wrote_file` (True/False) |
| 4 | What is `no_code_change_reason`? | `result.no_code_change_reason` |
| 5 | Did Guardrail trigger? | Look for "Completion claimed without write_file" in logs |

**Root causes:**
- Agent entered "analysis mode" (read-only intent)
- Agent claimed completion without tool evidence
- Budget exhausted before write_file step
- LLM chose to explain instead of act

**Fix:**
- Guardrail auto-injects correction prompt (70% success rate)
- For persistent failures: improve prompt to emphasize "write_file is required for code modification tasks"
- Check `_is_code_modification_task()` pattern matching

**Real example (D34 self-testing):**
> Task: "Fix the bug in bubble_sort.py"
> Agent read code, ran tests, searched — 7 tool calls, 0 write_file
> Guardrail: "Completion claimed without write_file, injecting correction"
> Result: Agent still didn't write (LLM-dependent, DeepSeek Reasoner sometimes prioritizes analysis)

---

## 2. Agent Selected Wrong File

**Symptoms:** Agent modified a file, but tests still fail or `git_diff` shows wrong changes.

**Diagnosis steps:**

| Step | Check | Tool |
|------|-------|------|
| 1 | Which file did search_code return? | `result.steps` → `tool_name == "search_code"` |
| 2 | Which file did read_file open? | `result.steps` → `tool_name == "read_file"` |
| 3 | Which file did write_file modify? | `result.steps` → `tool_name == "write_file"` |
| 4 | Is the file path correct? | Compare against workspace index |
| 5 | Are there similar files? | `search_code` may return multiple matches |

**Root causes:**
- Similar function names across files (e.g., `helper.py` vs `utils.py`)
- Filename ambiguity (e.g., `test_main.py` in multiple directories)
- SmartFileResolver chose wrong candidate

**Fix:**
- Agent uses `read_file` to verify content before writing
- WorkspaceIndex provides AST summaries for disambiguation
- If ambiguous, agent should search more specifically (add file_pattern)

**Real example (D34 self-testing):**
> Task: "Add error handling to fibonacci.py"
> search_code returned matches in fibonacci.py, test_fibonacci.py, lcm.py
> Agent resolved by: read_file first → confirmed target → wrote correct file

---

## 3. run_tests Failure

**Symptoms:** `run_tests` returns `success=False` or `failed > 0`.

**Diagnosis steps:**

| Step | Check | What to Look For |
|------|-------|-----------------|
| 1 | stdout | Error traceback, assertion messages |
| 2 | stderr | Import errors, syntax errors |
| 3 | return_code | 0=pass, 1=fail, 2=collection error |
| 4 | Duration | >30s suggests timeout or infinite loop |

**Common error types:**

| Error | Likely Cause | Fix |
|-------|-------------|-----|
| `ModuleNotFoundError` | Import path wrong, missing dependency | Check `sys.path`, `requirements.txt` |
| `AssertionError` | Code logic wrong | Read assertion message, fix code |
| `SyntaxError` | Write_file introduced syntax error | Re-read file, fix syntax |
| `ImportError` | Circular import or wrong import | Check import chain |
| `Timeout` | Infinite loop or slow test | Add timeout, check loop bounds |
| `Collection error` | `uploads/` conflict (D34.1 fix) | Check `conftest.py` collect_ignore |

**Key behavior:** Agent's `Observation` field contains the test output. In the ReAct loop, this feeds back into the next LLM call, so the agent sees the error and can retry.

---

## 4. LLM No Response or Timeout

**Symptoms:** Agent hangs, returns empty answer, or raises `LLMClientError`.

**Diagnosis steps:**

| Step | Check | Where |
|------|-------|-------|
| 1 | Retry logs | `logger.warning("Request failed: ... (attempt 1/2)")` |
| 2 | Timeout config | `settings.llm_timeout_seconds` (default 30) |
| 3 | API key | `settings.llm_api_key` — is it set? |
| 4 | Error type | Timeout / 429 / 5xx / 400 / auth |

**Error classification:**

| Error | Retries | Action |
|-------|---------|--------|
| Timeout | Yes (2x) | Check network, increase timeout |
| Connection error | Yes (2x) | Check base_url, DNS |
| 429 Rate limit | Yes (Retry-After) | Wait, reduce request rate |
| 5xx Server error | Yes (2x) | Check provider status page |
| 400 Bad request | No | Check payload, model name |
| 401/403 Auth | No | Check API key |

**Interview answer:**
> LLM client has configurable timeout (30s default) and retry (2 attempts with 1s backoff). 429 uses Retry-After header. 400/auth errors don't retry — they're client errors. Final failure raises `LLMClientError` with full context.

---

## 5. Memory Not Working

**Symptoms:** Agent doesn't recall previous tasks, memory API returns empty.

**Diagnosis steps:**

| Step | Check | Where |
|------|-------|-------|
| 1 | Memory loaded? | Startup log: "Memory loaded: X tasks, Y errors" |
| 2 | File exists? | `data/memory/memory_store.json` |
| 3 | File corrupted? | `logger.warning("Failed to load memory file")` |
| 4 | Search returns results? | `GET /api/memory/search?q=...` |
| 5 | Embedding model available? | `sentence-transformers` installed? |

**Degradation behavior:**
- Missing file → empty memory, normal startup
- Corrupted file → warning + fallback empty memory
- Embedding unavailable → vector search skipped, structured search still works
- Memory write fails → in-memory continues, warning logged

**Interview answer:**
> Memory is an enhancement layer. If JSON is missing or corrupted, the agent starts with empty memory and functions normally. Structured memory (keyword matching) works without any external dependencies. Vector memory (FAISS + sentence-transformers) is optional — if unavailable, the system falls back to keyword-only search.

---

## 6. Docker Startup Failure

**Symptoms:** `docker compose up` fails or container exits immediately.

**Diagnosis steps:**

| Step | Command | What to Check |
|------|---------|---------------|
| 1 | `docker compose logs codepilot` | Startup errors, import errors |
| 2 | `docker compose ps` | Status (running/exited/healthy) |
| 3 | `.env` | API key, base URL, model |
| 4 | Port check | `lsof :8000` or `netstat -ano | findstr :8000` |
| 5 | Volume path | Does `./workspace` exist on host? |

**Common issues:**

| Issue | Symptom | Fix |
|-------|---------|-----|
| Missing .env | `LLM_API_KEY 未配置` | Create `.env` from `.env.example` |
| Port occupied | `Address already in use` | Kill other process or change port |
| Volume missing | `No such file or directory` | `mkdir workspace` |
| Import error | `ModuleNotFoundError` | Check requirements.txt, rebuild image |
| Health check fail | Unhealthy status | Check `/health` endpoint, logs |

**Interview answer:**
> Docker setup is for demo/evaluation, not production. `docker compose up -d --build` builds the image, maps port 8000, mounts workspace volume, and starts uvicorn. Health check polls `/health` every 10s. Debug with `docker compose logs -f codepilot`.

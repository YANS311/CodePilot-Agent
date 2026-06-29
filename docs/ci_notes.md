# CI Notes

> Transparency document for GitHub Actions CI behavior and conditional test skips.

---

## 1. What CI Runs

**Workflow:** `.github/workflows/ci.yml`

| Setting | Value |
|---------|-------|
| Trigger | push / pull_request to main/master |
| Runner | ubuntu-latest |
| Python | 3.11 |
| Command | `pytest tests/ -q` |
| pip cache | Enabled |

CI installs dependencies from `requirements.txt` and runs the full pytest collection. Tests that cannot run in CI are conditionally skipped — they are not disabled or removed.

---

## 2. Why Some Tests Are Conditionally Skipped

Three categories of tests require dependencies that are intentionally unavailable in CI:

### 2.1 External LLM API

Tests that call the real LLM endpoint (e.g., `test_upload_api.py::TestChatWorkspaceId`) need a valid API key. CI sets `CODEPILOT_LLM_API_KEY=dummy` — no real API calls are made. These tests are skipped with reason: `LLM API key not configured`.

### 2.2 Local Embedding Model

Tests that depend on `sentence-transformers` model loading (e.g., embedding router classification, agent multi-step routing, vector normalization) require the model to be downloaded and cached. CI does not pre-download the model to avoid network dependency and slow builds. These tests are skipped with reason: `sentence-transformers model not available` or `Intent router needs embedding model for correct routing`.

### 2.3 Local-Only Documents

Tests that validate local interview docs (`docs/system_summary.md`, `docs/interview_onepager.md`) are skipped in CI because these files are in `.gitignore` — they exist only on the developer's local machine. Skip reason: `local-only docs absent`.

---

## 3. Local vs CI Testing

| Aspect | Local | CI |
|--------|-------|-----|
| Python version | 3.9 (developer) | 3.11 (matrix) |
| LLM API key | Configured | Dummy (skipped) |
| Embedding model | Cached locally | Not downloaded (skipped) |
| Local docs | Present | Gitignored (skipped) |
| Expected result | 516 passed, 2 skipped | Green with conditional skips |

**Local full environment:** 516 passed, 2 skipped — all tests including those that need external dependencies.

**CI environment:** Green — core logic, API routing, tool execution, memory, workspace indexing, and non-external tests all pass. Tests requiring external LLM, embedding model, or local docs are skipped with clear reasons.

CI validates the same codebase. The difference is environmental, not functional.

---

## 4. Skip Reason Audit

Every `pytest.mark.skipif` in the test suite has a reason string that explains:

| Test File | Skip Condition | Reason |
|-----------|---------------|--------|
| `test_system_summary.py` | `not _HAS_SYSTEM_SUMMARY` | `docs/system_summary.md not in git checkout (local-only)` |
| `test_system_summary.py` | `not _HAS_ONEPAGER` | `docs/interview_onepager.md not in git checkout (local-only)` |
| `test_intent_router.py` | `not _HAS_EMBEDDING_MODEL` | `sentence-transformers model not available` |
| `test_vector_memory.py` | `not HAS_MODEL` | `sentence-transformers model not available` |
| `test_agent.py` | `not _HAS_EMBEDDING_MODEL` | `Intent router needs embedding model for correct routing` |
| `test_d7_advanced.py` | `not _HAS_EMBEDDING_MODEL` | `Intent router needs embedding model for correct routing` |
| `test_d76_demo.py` | `not _HAS_EMBEDDING_MODEL` | `Intent router needs embedding model for correct routing` |
| `test_upload_api.py` | `not _HAS_LLM` | `LLM API key not configured` |

No test is skipped without a reason. No pure unit test is skipped — only tests with external dependencies.

---

## 5. Future Improvements

These are known gaps that could improve CI coverage:

1. **Deterministic mock embedding model** — Provide a lightweight mock `EmbeddingModel` that returns fixed vectors. This would allow embedding router and agent routing tests to run in CI without downloading `sentence-transformers`.

2. **Mock LLM provider** — A mock `LLMClient` that returns scripted responses for integration tests. Currently, agent tests mock at the Python level (`AsyncMock`), but API-level tests (like `test_chat_with_workspace_id`) hit the real endpoint.

3. **Split CI into unit / integration / external jobs** — Separate fast unit tests (always green) from integration tests (need mocks) and external tests (need real API). This would make CI faster and clearer about what each job validates.

These improvements are not implemented yet. The current CI is sufficient for validating core logic correctness.

---

## 6. How to Run Locally

```bash
# Full test suite (requires embedding model + LLM API key)
pytest tests/ -v

# Quick check (same as CI)
pytest tests/ -q

# Skip external-dependency tests manually
pytest tests/ -q -k "not (TestEmbeddingRouting or TestAgentSingleToolCall)"
```

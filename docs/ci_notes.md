# CI Notes

> Transparency document for GitHub Actions CI behavior, test layering, and conditional skips.

---

## 1. CI Design Principle

- CI prioritizes **determinism** over completeness
- External dependencies (LLM API, embedding model) are mocked in CI mode
- Integration tests are isolated from external services
- Full system evaluation runs locally with real models

---

## 2. Test Architecture

```
tests/
├── unit/          # 100% CI — deterministic, no external deps
├── integration/   # CI with mock deps — may skip if real deps needed
└── e2e/           # Local only — never in CI
```

| Layer | CI Behavior | Local Behavior |
|-------|------------|----------------|
| `unit/` | Always runs, 0 skips | Always runs |
| `integration/` | Runs with CI_MODE=true (mock deps) | Runs with real deps, may skip if unavailable |
| `e2e/` | Not included in CI | Runs locally |

---

## 3. CI Mode (`CODEPILOT_CI_MODE=true`)

When `CODEPILOT_CI_MODE=true` is set:

| Component | Normal Mode | CI Mode |
|-----------|------------|---------|
| Embedding Model | sentence-transformers (real) | FixedEmbeddingModel (deterministic hash) |
| LLM Client | OpenAI/DeepSeek API | MockLLMProvider (deterministic response) |
| API Key | Required | Not required |

This allows all integration tests to run in CI without downloading models or calling APIs.

---

## 4. What CI Runs

**Workflow:** `.github/workflows/ci.yml`

| Setting | Value |
|---------|-------|
| Trigger | push / pull_request to main/master |
| Runner | ubuntu-latest |
| Python | 3.11 |
| CI Mode | `CODEPILOT_CI_MODE=true` |
| Steps | `pytest tests/unit -q` then `pytest tests/integration -q` |
| e2e tests | Not included |

---

## 5. Skip Governance

All `pytest.mark.skipif` must use one of these standardized reasons:

| Reason | When to Use |
|--------|------------|
| `"external dependency unavailable: sentence-transformers model"` | Embedding model not available |
| `"external dependency unavailable: LLM API key"` | LLM API key not configured |
| `"external dependency unavailable: Docker"` | Docker not available |
| `"optional integration test: local-only docs"` | Local-only documents missing |
| `"CI mode limitation"` | CI-specific constraints |

Every skip reason is printed in the pytest terminal summary via the skip reporter in `tests/conftest.py`.

---

## 6. Metric Consistency

All evaluation metrics must distinguish their source:

| Metric Source | Environment | Description |
|--------------|-------------|-------------|
| CI metrics | GitHub Actions | Deterministic, mock deps |
| Local metrics | Developer machine | Real embedding + LLM |
| Stress metrics | Manual run | Multi-file, retry, recovery |

---

## 7. Failure Observability

All agent exceptions are recorded as `AgentErrorEvent`:

```python
@dataclass
class AgentErrorEvent:
    module: str           # "react_agent" / "llm_client" / "tool"
    error_type: str       # Exception class name
    context: str          # What was happening
    tool_name: str        # Which tool (if applicable)
    recovery_action: str  # What recovery was attempted
```

Error events are stored in `AgentRunResult.error_events` and visible in the eval system.

---

## 8. Future Improvements

1. **Deterministic mock embedding model** — ✅ Implemented as `FixedEmbeddingModel`
2. **Mock LLM provider** — ✅ Implemented as `MockLLMProvider`
3. **Split CI into unit / integration / e2e** — ✅ Implemented
4. **Skip reason standardization** — ✅ Implemented
5. **Failure observability** — ✅ Implemented as `AgentErrorEvent`

---

## 9. How to Run Locally

```bash
# Unit tests only (fast, no external deps)
pytest tests/unit -q

# Integration tests (needs embedding model or CI_MODE)
pytest tests/integration -q

# E2E tests (needs full local environment)
pytest tests/e2e -q

# Full suite
pytest tests/ -q

# With CI mode (mock deps)
CODEPILOT_CI_MODE=true pytest tests/unit tests/integration -q
```

# v0.4.3 — CI Quality Gate Patch

## GitHub Actions

* Added `.github/workflows/ci.yml`
  * Triggers on push and pull_request to main/master
  * Runs on ubuntu-latest with Python 3.11
  * pip cache enabled
  * Installs dependencies from requirements.txt
  * Runs `pytest tests/ -q`
  * Dummy LLM env vars (no real API calls)

## Dependencies

* Added missing dependencies to `requirements.txt`:
  * `numpy` — used by vector memory and embedding router
  * `sentence-transformers` — used by embedding model
  * `python-multipart` — required by FastAPI for file uploads
  * `pytest-asyncio` — required for async test functions

## Tests

* Added skip conditions for tests that depend on:
  * Local-only docs (gitignored `system_summary.md`, `interview_onepager.md`)
  * Embedding model availability (sentence-transformers)
  * LLM API key configuration
* 516 passed, 2 skipped (same as v0.4.2)

## README

* Added CI badge linking to GitHub Actions workflow
* Added one-line description: "CI runs the full pytest suite on push and pull request."

## Notes

This is a CI-only patch. No Agent runtime behavior was changed.

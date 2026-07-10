# v0.4.4 — CI Transparency Patch

## Documentation

* Fixed README CI description — replaced "full pytest suite" with accurate description of conditional skips
* Added link to `docs/ci_notes.md` in README CI section
* Added `docs/ci_notes.md` — transparency document covering:
  * What CI runs (workflow, Python version, command)
  * Why some tests are conditionally skipped (LLM API, embedding model, local docs)
  * Local vs CI testing comparison
  * Skip reason audit table
  * Future improvements (mock embedding, mock LLM, CI job split)

## Notes

This is a docs-only patch. No code, tests, or Agent behavior was changed.

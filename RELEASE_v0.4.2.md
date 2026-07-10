# v0.4.2 — Interview Documentation Patch

## Documentation

* Added `docs/engineering_interview_audit.md`

  * Docker Compose lifecycle and troubleshooting notes
  * Memory/cache degradation behavior
  * LLM timeout, retry, backoff, and error handling notes

* Added `docs/git_interview_notes.md`

  * Merge vs rebase
  * Cherry-pick usage
  * Revert vs reset
  * Runtime file hygiene
  * CodePilot main/master branch sync example

* Added `docs/agent_failure_playbook.md`

  * Agent no-write diagnosis
  * Wrong-file recovery checklist
  * `run_tests` failure handling
  * LLM timeout/API failure diagnosis
  * Memory retrieval troubleshooting
  * Docker startup failure checklist

## README

* Added an "Engineering Notes for Interview" section linking to the new documentation.

## Tests

* 516 passed, 2 skipped

## Notes

This is a documentation-only release. No Agent runtime behavior was changed.

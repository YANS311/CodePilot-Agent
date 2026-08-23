---
name: bug-fix
description: Diagnose and fix reproducible software defects following systematic verification.
version: 1.0.0
tags: [debugging, bug-fix, repair, verification]
---

# Procedural Knowledge: Bug Fixing Workflow

When tasked with resolving a software defect, follow this strict 6-phase engineering process:

## Phase 1: Reproduce & Observe
1. Locate existing unit/integration tests or execute `run_tests` to observe the failing assertion or exception traceback.
2. Confirm the failure symptoms before modifying any implementation files.

## Phase 2: Root Cause Analysis
1. Use `search_code` to trace symbol definitions, call sites, and edge conditions.
2. Use `read_file` with precise line ranges to inspect the suspect implementation logic.
3. Formulate a clear hypothesis explaining *why* the defect occurs.

## Phase 3: Minimal Surgical Patch
1. Apply the most focused and minimal change required using `code_edit` or `write_file`.
2. Do not refactor unrelated code, comments, or formatting.
3. Preserve backwards compatibility with existing callers.

## Phase 4: Targeted Verification
1. Re-run the specific failing test suite via `run_tests(target=...)`.
2. Confirm that the previously failing test now passes.

## Phase 5: Regression & Side-Effect Check
1. Execute `git_diff` to review all changes and verify no unintended modifications occurred.
2. Run related tests across the workspace to ensure zero regressions were introduced.

## Phase 6: Concise Summary
1. Summarize the root cause, what was changed, and which tests verified the fix.

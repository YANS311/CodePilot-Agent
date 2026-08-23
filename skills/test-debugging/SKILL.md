---
name: test-debugging
description: Isolate flaky or failing tests, analyze stack traces, and systematically eliminate test failures.
version: 1.0.0
tags: [testing, debugging, pytest, failure-isolation]
---

# Procedural Knowledge: Test Debugging Workflow

When debugging complex test failures or assertion mismatches:

## Phase 1: Isolated Test Execution
1. Run only the specific failing test function with verbose output: `run_tests(target="path/to/test_file.py::test_name")`.
2. Inspect the exact assertion error, expected vs actual values, and stack trace line numbers.

## Phase 2: Failure Clustering & Hypothesis
1. Check if multiple tests fail due to the same underlying mock or environment dependency.
2. Determine if the failure is caused by code defect, fixture setup mismatch, or environment state.

## Phase 3: Surgical Fix & Re-run Loop
1. Modify the test fixture or implementation file using surgical `code_edit`.
2. Immediately rerun the isolated test to verify resolution.
3. Once the single test passes, run the entire test module to ensure no collateral breaks.

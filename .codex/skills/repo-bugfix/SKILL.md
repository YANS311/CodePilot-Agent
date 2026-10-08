---
name: repo-bugfix
description: Systematically diagnose, fix, and verify FastAPI backend issues. Use for bug fix, debugging, error, exception, failing tests, 修复, 调试, 报错, API failures, regressions, and unexpected behavior.
---

# Repo Bugfix

Use this skill to investigate and resolve defects in this repository with a reproducible, minimal-change workflow.

## Applicable scenarios

Apply this skill when the user reports a bug, exception, API error, failing test, regression, or behavior that differs from expectations. Also apply it when the user asks to locate the cause of such a problem.

If the request is diagnosis-only, stop after explaining the cause and impact. Do not edit files unless the user also asks for a fix.

## Required references

Read [references/debugging-workflow.md](references/debugging-workflow.md) before starting the investigation. It defines the five required phases and repository-specific verification commands.

Read [references/failure-patterns.md](references/failure-patterns.md) when classifying symptoms, choosing search targets, or interpreting a failed verification. Use only the sections relevant to the observed failure.

## Workflow

Follow all five phases in order:

1. Understand the problem: obtain the exact error and establish expected behavior.
2. Analyze the code: search related code, read its context, and identify the affected scope.
3. Fix: prefer the smallest behavior-focused change and avoid unrelated refactoring.
4. Verify: run relevant tests, analyze failures, and inspect the final Git diff.
5. Summarize: report the cause, changed files, test results, and follow-up recommendations.

Do not skip directly from a symptom to an edit. If evidence changes the working hypothesis, return to analysis and update the suspected impact scope.

## Tool constraints

- Use `rg` or `rg --files` first for repository searches. Use a fallback only if `rg` is unavailable.
- Prefer `apply_patch` for focused file edits.
- Preserve existing architecture and unrelated user changes. Never discard or overwrite a dirty worktree to make the fix easier.
- Use the repository's configured conda Python for Python and pytest commands.
- Start with the narrowest relevant test, then widen verification according to risk.
- Do not use Docker unless the defect specifically requires container isolation or a Docker runner check.
- Inspect `git diff` and `git status --short` before declaring the fix complete. Do not stage or commit unless the user asks.
- Treat missing optional LLM keys, embedding models, Docker, and local-only documentation as environment limitations unless the task concerns those paths.

## Output contract

End with a concise, evidence-based summary containing:

- **Root cause:** what was wrong and why it produced the symptom.
- **Changed files:** each modified file and its purpose, or `None` for diagnosis-only work.
- **Tests:** commands run and their pass, fail, or skip results; clearly state anything not run.
- **Follow-up:** remaining risks or recommended next actions, or `None` when no follow-up is needed.

Do not claim success when verification is incomplete. Distinguish product failures from environment or dependency failures.

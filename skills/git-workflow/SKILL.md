---
name: git-workflow
description: Automate conventional commit formatting, branch conflict detection, and git hygiene.
version: 1.0.0
tags: [git, commit, conflict, branch, rebase, merge, changelog]
---

# Procedural Knowledge: Git Workflow & Conflict Resolution

When managing branches, resolving merge/rebase conflicts, or preparing pull requests:

## Phase 1: Conflict & Hygiene Check
1. Execute conflict detector helper script:
   `python skills/git-workflow/scripts/conflict_detector.py <target_directory_or_repo>`
2. Inspect for unresolved conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`).

## Phase 2: Git Status & Diff Triage
1. Run `git_status` to see untracked, modified, or staged files.
2. Run `git_diff` to audit line-by-line changes against the target branch (e.g. `main`).

## Phase 3: Conventional Commit Standard
Format commit titles and PR descriptions according to `skills/git-workflow/references/conventional_commits.md`:
- `feat:` New user-facing feature or tool
- `fix:` Bug fix or defect patch
- `test:` Unit/integration test additions
- `refactor:` Code restructuring without behavior change
- `docs:` Documentation or README updates
- `ci:` Pipeline, GitHub Actions, or CD delivery updates

## Phase 4: Pre-commit Verification
1. Run automated unit tests before staging changes.
2. Ensure no test pollution or temporary files remain unstaged.

# Conventional Commits Reference Guide

Specification for creating standardized, machine-readable commit messages and release notes.

---

## Commit Message Format

```text
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

### Common Types

| Type | Description |
|---|---|
| `feat` | Introduces a new feature or user-facing capability. |
| `fix` | Patches a bug or resolves an unexpected defect. |
| `docs` | Documentation-only changes (e.g. README, docstrings). |
| `refactor` | Code restructuring without fixing bugs or adding features. |
| `test` | Adding missing tests or correcting existing tests. |
| `ci` | Changes to CI/CD workflows, build scripts, or deployment configs. |
| `chore` | Routine repository maintenance, dependency bumps. |

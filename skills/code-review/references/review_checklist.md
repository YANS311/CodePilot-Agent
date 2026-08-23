# Code Review Verification Checklist

- [ ] **Security**: No hardcoded credentials, unchecked path traversals, or dangerous shell evaluations.
- [ ] **Architecture**: Respects `BaseTool` contracts, Dependency Injection, and error envelope formats.
- [ ] **Type Hints & Contracts**: Functions have explicit type annotations and docstrings.
- [ ] **Test Coverage**: Critical code paths have corresponding unit and integration tests.
- [ ] **Zero Regression**: Clean `git_diff` with no leftover scratch files or debugging print statements.

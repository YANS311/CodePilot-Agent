# Pytest Common Pitfalls & Debugging Cheatsheet

1. **Async Test Fixtures**: Ensure `@pytest.mark.asyncio` is applied when testing coroutines.
2. **Mock Cleanup**: Use `monkeypatch` or `unittest.mock.patch` with context managers to avoid test pollution across suite runs.
3. **Floating Point Assertions**: Use `pytest.approx(expected)` instead of strict equality `==`.
4. **Temporary Directory Isolation**: Use `tmp_path` fixture instead of hardcoding temporary folders.

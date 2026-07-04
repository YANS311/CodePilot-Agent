"""verification.py — Self-verifying agent loop policy.

After the agent writes a file, automatically run tests. If tests fail,
feed the failure log back to the agent and let it retry. This closes
the fix → test → verify loop without external orchestration.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class VerificationPolicy:
    """Controls the post-write test verification behavior.

    Attributes:
        enabled: Whether verification runs at all.
        max_retries: How many times the agent may retry after a test failure.
        test_command: Optional override for the pytest target (e.g. "tests/test_foo.py").
        stop_on_pass: If True, stop the entire loop on first passing test run.
    """

    enabled: bool = False
    max_retries: int = 2
    test_command: str | None = None
    stop_on_pass: bool = True

    @classmethod
    def disabled(cls) -> VerificationPolicy:
        """Return a policy that skips verification entirely."""
        return cls(enabled=False)

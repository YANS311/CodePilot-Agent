# Bug Reproduction & Root Cause Guide

1. **Deterministic Reproduction**: Always reproduce the defect via an automated test or minimal script before editing source code.
2. **Minimal Failure Slice**: Strip away extraneous logic to find the minimal input causing the failure.
3. **Traceback Reading**: Read the innermost frame first, check the local variable state at the time of exception.
4. **Surgical Verification**: Verify the patch fixes the defect while keeping all existing tests green.

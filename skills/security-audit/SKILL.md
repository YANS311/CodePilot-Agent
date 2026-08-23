---
name: security-audit
description: Audit source code for security vulnerabilities, hardcoded secrets, SQL injection, and path traversal defects.
version: 1.1.0
tags: [security, audit, vulnerability, cwe, owasp, secrets, injection]
---

# Procedural Knowledge: Security & Vulnerability Audit Workflow

When tasked with conducting a security audit or hunting for vulnerabilities in a codebase:

## Phase 1: Automated Secret & Pattern Scan
1. Execute the built-in scanner helper script:
   `python skills/security-audit/scripts/secret_scanner.py <target_directory_or_file>`
2. Inspect the scanner findings for high-confidence secrets (API keys, JWT tokens, private keys, database passwords).

## Phase 2: Input Validation & Injection Surface Analysis
1. Inspect database query construction for unparameterized SQL strings (CWE-89).
2. Check file access operations for unsanitized relative paths or path traversal (CWE-22) using `read_file` or `search_code`.
3. Check dynamic code execution surfaces (`eval`, `exec`, `subprocess(shell=True)`) for command injection (CWE-78).

## Phase 3: Reference CWE / OWASP Standards
1. Review `skills/security-audit/references/owasp_cwe_cheatsheet.md` to map detected patterns against standard CWE taxonomy.
2. Determine risk severity: `CRITICAL`, `HIGH`, `MEDIUM`, or `LOW`.

## Phase 4: Verification & Safe Reproduction
1. Formulate safe, non-destructive test cases or assertions demonstrating the defect without causing environment damage.
2. Verify why current guards or filters failed to catch the issue.

## Phase 5: Remediation & Hardening Report
1. Apply parameterized queries, path canonicalization (`Path.resolve()` boundary checks), or environment variable abstraction.
2. Format the final output into:
   - **Executive Summary**: Total vulnerabilities found by severity.
   - **Vulnerability Breakdown**: Vulnerability type, CWE ID, affected file/line, root cause, and minimal patch.
   - **Verification Results**: Tests demonstrating the fix is secure and introduces no regressions.

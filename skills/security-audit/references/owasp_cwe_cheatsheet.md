# OWASP & CWE Top Security Vulnerabilities Cheatsheet

A concise reference guide for common software vulnerabilities, mitigation patterns, and verification tests.

---

## 1. CWE-22: Improper Limitation of a Pathname to a Restricted Directory (Path Traversal)

### Symptom
Unsanitized user inputs used directly in filesystem operations:
```python
# VULNERABLE
with open(f"workspace/{user_filename}", "r") as f:
    return f.read()
```

### Remediation
Always canonicalize paths and verify the boundary check:
```python
# REMEDIATION
base_dir = Path("workspace").resolve()
target = (base_dir / user_filename).resolve()
if not str(target).startswith(str(base_dir)):
    raise PermissionError("Access denied: Path outside boundary")
```

---

## 2. CWE-798: Use of Hard-coded Credentials

### Symptom
Direct string assignment of tokens, API keys, or database passwords:
```python
# VULNERABLE
AWS_SECRET = "AKIAIOSFODNN7EXAMPLE"
DB_PASS = "admin123456"
```

### Remediation
Load from environment variables with fallback guards:
```python
# REMEDIATION
import os
AWS_SECRET = os.environ.get("AWS_SECRET_KEY")
if not AWS_SECRET:
    raise ValueError("Missing AWS_SECRET_KEY in environment")
```

---

## 3. CWE-78: Improper Neutralization of Special Elements used in an OS Command (OS Command Injection)

### Symptom
Invoking shell commands with string interpolation and `shell=True`:
```python
# VULNERABLE
subprocess.run(f"git clone {repo_url}", shell=True)
```

### Remediation
Pass command arguments as an array and disable shell:
```python
# REMEDIATION
subprocess.run(["git", "clone", repo_url], shell=False, check=True)
```

---

## 4. CWE-89: SQL Injection

### Symptom
Concatenating raw user inputs into SQL query strings:
```python
# VULNERABLE
cursor.execute(f"SELECT * FROM users WHERE username = '{username}'")
```

### Remediation
Use parameterized queries:
```python
# REMEDIATION
cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
```

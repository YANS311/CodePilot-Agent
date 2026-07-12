# CodePilot Commands

## Python

Use this interpreter by default:

```powershell
C:\Users\A\anaconda3\envs\mini_coding_agent\python.exe
```

## Targeted Checks

Run a focused unit test:

```powershell
C:\Users\A\anaconda3\envs\mini_coding_agent\python.exe -m pytest -p no:cacheprovider tests\unit\test_run_tests.py -q
```

Compile a changed Python file:

```powershell
C:\Users\A\anaconda3\envs\mini_coding_agent\python.exe -m py_compile app\tools\run_tests.py
```

## CI-Equivalent Local Checks

GitHub Actions runs unit and integration tests separately:

```powershell
C:\Users\A\anaconda3\envs\mini_coding_agent\python.exe -m pytest tests\unit -q --tb=short
C:\Users\A\anaconda3\envs\mini_coding_agent\python.exe -m pytest tests\integration -q --tb=short
```

When reproducing CI behavior locally, set `CODEPILOT_CI_MODE=true`.

## Eval Replay

Replay one or more tasks:

```powershell
C:\Users\A\anaconda3\envs\mini_coding_agent\python.exe scripts\replay_task.py fix-retry-request
C:\Users\A\anaconda3\envs\mini_coding_agent\python.exe scripts\replay_task.py fix-append-line fix-file-processor-all
```

Replay all failed tasks from `reports/eval_report.json`:

```powershell
C:\Users\A\anaconda3\envs\mini_coding_agent\python.exe scripts\replay_task.py --all-failed
```

## Reports And Artifacts

- Commit curated replay traces under `reports/replays/` when they support a deliberate fix.
- Do not commit timestamped generated benchmark reports under `benchmarks/real_world/reports/eval_*.json` or `eval_*.md`.
- Keep `.gitignore` precise; do not ignore source seed directories such as `workspace/examples/`.

## Docker

Use Docker only when local isolation is material to the task:

```powershell
docker info
docker compose up -d --build
docker compose logs -f codepilot
```

If Docker is unavailable, report that limitation and use the conda path for ordinary Python validation.

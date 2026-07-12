# CodePilot Agent Workspace Guide

## Project Shape

CodePilot Agent is a FastAPI-based ReAct coding-agent prototype. The core loop lives in `app/agent/`, tools live in `app/tools/`, evaluation code lives in `app/evaluation/`, and reusable workspace seed files live in `workspace/`.

## Environment

- Prefer the local conda environment when running Python commands:
  `C:\Users\A\anaconda3\envs\mini_coding_agent\python.exe`
- Use Docker only when the task specifically needs container isolation or a Docker runner check. Docker Desktop may not be running on this machine, so verify before relying on it.
- CI runs on Python 3.11 with `CODEPILOT_CI_MODE=true`.

## Verification

- Fastest targeted unit check:
  `C:\Users\A\anaconda3\envs\mini_coding_agent\python.exe -m pytest -p no:cacheprovider tests\unit\test_name.py -q`
- CI-equivalent local check:
  `C:\Users\A\anaconda3\envs\mini_coding_agent\python.exe -m pytest tests\unit tests\integration -q --tb=short`
- Full local suite can include e2e tests and optional external dependencies. Do not treat local skips for missing LLM keys, embedding models, Docker, or local-only docs as CI regressions unless the task is about those paths.
- After editing `workspace/examples` or `workspace/tests`, run the specific affected tests or `py_compile` on changed Python files.

## Evaluation Workflow

- Replay known eval tasks with:
  `C:\Users\A\anaconda3\envs\mini_coding_agent\python.exe scripts\replay_task.py <task-id>`
- Common replay tasks include `fix-retry-request`, `fix-append-line`, and `fix-file-processor-all`.
- Replay outputs under `reports/replays/` are curated artifacts and may be committed when they document an intentional recovery path.
- Timestamped real-world benchmark outputs under `benchmarks/real_world/reports/eval_*.json` and `eval_*.md` are generated runtime artifacts and should stay ignored.

## Git And PR Flow

- Work from a feature branch for repo changes.
- Keep commits focused and include tests or validation notes in the PR body.
- Before pushing, check `git status --short` and avoid staging unrelated user files.
- If GitHub Actions fails, inspect the failing job first and fix the narrowest reproducible issue locally.

## Editing Conventions

- Preserve existing architecture: `ToolRegistry`, `BaseTool`, guarded workspace tools, and ReAct verification flow.
- Prefer small, behavior-focused tests near the affected layer.
- Do not refactor generated reports, interview docs, or historical release notes unless the task asks for it.
- Keep `.gitignore` rules precise; do not hide whole source directories such as `workspace/examples/`.

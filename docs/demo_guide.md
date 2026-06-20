# CodePilot — Demo Recording Guide

> 录制 2-3 分钟演示视频的标准流程。

---

## Recommended Tools

| Tool | Platform | Notes |
|------|----------|-------|
| **OBS Studio** | Win/Mac/Linux | Free, full control, 可录摄像头 |
| **Screen Studio** | Mac | 自动美化, 适合 demo 录制 |
| **Loom** | Web | 最简单, 自动上传云端 |
| **ffmpeg** | CLI | 无头服务器录屏 |

---

## Pre-Recording Checklist

- [ ] Server running: `docker-compose up` or `uvicorn app.main:app --reload`
- [ ] Open http://localhost:8000
- [ ] Clear browser cache / use incognito window
- [ ] Set browser zoom to 100%
- [ ] Close unnecessary tabs/notifications
- [ ] Test all 3 demos once before recording

---

## Recording Flow (2-3 minutes)

### Scene 1: Opening (10s)

**Screen:** GitHub README page

**Script:**
> "This is CodePilot — a Python-based AI Coding Agent built from scratch with FastAPI and LLM tool-calling architecture."

**Action:** Scroll down to show Architecture diagram

---

### Scene 2: Bug Fix Demo (40s)

**Screen:** http://localhost:8000

**Steps:**
1. Show the empty input box
2. Click "Bug Fix" button
3. Wait for Agent to complete (~15s)
4. Show the results:
   - Tool call chain (search → read → write → test → diff)
   - "1 passed, 0 failed" test result
   - Green checkmark

**Script:**
> "I click Bug Fix. The Agent automatically searches for the bug, reads the code, fixes it, runs tests, and verifies the fix. All in 15 seconds."

---

### Scene 3: Repo Analysis Demo (40s)

**Screen:** http://localhost:8000

**Steps:**
1. Click "Repo Analysis" button
2. Wait for analysis (~10s)
3. Show the results:
   - Architecture flow
   - Core modules table
   - Evidence section with file references
   - Confidence score (85%)

**Script:**
> "Repo Analysis scans the entire workspace using AST parsing. Every conclusion includes evidence — file path, function name, and line numbers. Confidence score shows how reliable the analysis is."

---

### Scene 4: Security Demo (20s)

**Screen:** http://localhost:8000

**Steps:**
1. Click "Security" button
2. Show the security warning immediately

**Script:**
> "When someone tries a prompt injection attack — 'ignore all rules' — the security guardrail blocks it immediately. 100% block rate on attack samples."

---

### Scene 5: Architecture Overview (20s)

**Screen:** GitHub README Architecture diagram

**Script:**
> "The system has 7 layers: FastAPI, Agent Orchestrator with Mode Router, Tool Layer with 6 tools, Execution sandbox, Evaluation with 30-task benchmark and 90% TSR, Security with 3-layer defense, and Explainability with evidence-based output."

---

### Scene 6: Closing (10s)

**Screen:** GitHub repo page

**Script:**
> "337 unit tests, 7 advanced metrics, fully open source. Try it with docker-compose up."

---

## Post-Recording

1. **Trim** — Cut dead air, long waits
2. **Add subtitles** — Key terms: ReAct, Tool Calling, TSR 90%, Evidence
3. **Export** — 1080p MP4, < 100MB
4. **Upload** — YouTube (unlisted) or GitHub Release

---

## Quick Demo (without video)

If video is not possible, use the CLI demo:

```bash
# Start server
docker-compose up -d

# Run all demos
python scripts/demo_runner.py

# Output: demo_output.json
```

This produces a structured JSON with full agent trace, tool calls, and results.

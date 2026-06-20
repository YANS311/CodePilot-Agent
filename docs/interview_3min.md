# CodePilot — 3-Minute Interview Script

> 面试官 3 分钟能听懂的项目讲解。

---

## 1. 一句话定义（10秒）

**CodePilot 是一个从零构建的 Python Coding Agent，能自动搜索代码、定位 bug、修复问题、运行测试，并给出带证据的分析报告。**

---

## 2. 为什么做这个项目（30秒）

**痛点：** 现有 AI 编程助手（Copilot、Cursor）是黑盒 —— 你不知道它改了什么、为什么改、是否正确。

**解决方案：** CodePilot 把 Agent 的每一步都变得可观测、可验证、可解释：

- **可观测**：每一步 Think → Act → Observe 都有完整日志
- **可验证**：自动运行测试确认修复正确
- **可解释**：每个结论附带代码证据（文件、函数、行号）

---

## 3. 核心架构（60秒）—— 只讲 4 层

```
┌─────────────────────────────────────────┐
│  1. Agent Layer                         │
│     Mode Router → ReAct Agent / Repo    │
│     Think → Act → Observe 循环          │
├─────────────────────────────────────────┤
│  2. Tool Layer                          │
│     6 tools: search / read / write      │
│     run_tests / git_diff / git_status   │
│     + Tool Guardrail (安全拦截)          │
├─────────────────────────────────────────┤
│  3. Evaluation Layer                    │
│     30-task benchmark                   │
│     TSR 90% | 7 advanced metrics        │
│     Error Taxonomy 自动归因              │
├─────────────────────────────────────────┤
│  4. Explainability Layer                │
│     AST Evidence Extraction             │
│     结论 → 文件 → 函数 → 行号           │
│     Confidence Score (0.0~1.0)          │
└─────────────────────────────────────────┘
```

**讲法：**

> "整个系统分 4 层。最上面是 Agent Layer，我实现了一个 Mode Router 做意图检测 —— 用户说'修 bug'走 ReAct 模式，说'项目做什么'走 Repo 分析模式。Agent 通过 Tool Layer 调用 6 个工具来操作代码。所有修改都会通过 Evaluation Layer 的 30 个测试任务验证。最下面是 Explainability Layer —— 每个分析结论都附带代码证据，用 AST 解析提取具体的文件、函数名和行号。"

---

## 4. Demo 流程（60秒）—— 完整链路

**标准 Demo Flow：上传 repo → 分析 → 修 bug → verify → explain**

```
Step 1: 上传一个有 bug 的 Python 项目
        ↓
Step 2: Agent 自动构建 WorkspaceIndex
        (文件树 + 每个文件前 200 行摘要)
        ↓
Step 3: 点击 "Repo Analysis" 按钮
        Agent 分析项目结构
        输出: 模块职责 + 执行流程 + Evidence
        ↓
Step 4: 点击 "Bug Fix" 按钮
        Agent 执行:
        Think: "subtract 返回 a+b, 应该是 a-b"
        Act:   write_file("a - b")
        Act:   run_tests() → 1 passed, 0 failed
        Act:   git_diff → +1 -1
        ↓
Step 5: 前端展示完整结果:
        ✅ 修复成功 + 测试通过
        📋 Evidence: app/calc.py → subtract() → L15
        🎯 Confidence: 85%
```

**讲法：**

> "我给你演示一个完整流程。首先上传一个有 bug 的计算器项目。Agent 自动构建文件索引。然后我点 Repo Analysis —— 它分析整个项目结构，输出模块职责和执行流程，每个结论都附带代码证据。接着我点 Bug Fix —— Agent 自动定位到 subtract 函数，发现它返回 a+b 而不是 a-b，自动修复并运行测试验证。前端展示完整的执行轨迹和证据链。"

---

## 5. 三个亮点（60秒）

### 亮点 1: Evaluation（TSR 90%）

> "我构建了一个 30 个任务的自动化评测框架，覆盖 Easy/Medium/Hard 三个难度。Task Success Rate 达到 90%。更重要的是定义了 7 个高级指标 —— 不只是看'有没有通过'，还看工具调用是否合法、修改后是否验证、安全拦截率等。"

### 亮点 2: Security（100% Block Rate）

> "我实现了 3 层安全防护：Prompt Injection 检测拦截恶意输入、Tool Guardrail 阻止危险操作（如删除文件、网络请求）、Completion Chain 验证确保修复是实际执行的而不是嘴上说说。安全攻击样例的拦截率是 100%。"

### 亮点 3: Explainability（Evidence-based）

> "这是最有差异化的点。现有 Agent 是黑盒输出，我的 Agent 每个结论都附带代码证据 —— 用 AST 解析提取函数名、行号、代码片段，计算置信度评分。面试官问'你怎么知道这个结论是对的'，我可以指着 evidence 说：因为 Agent 引用了 app/calc.py 第 15 行的 subtract 函数。"

---

## 6. 收尾（10秒）

> "总结一下：CodePilot 不只是一个能修 bug 的 Agent，它是一个完整的 Coding Agent 系统 —— 有评测、有安全、有可解释性。311 个单元测试，所有核心模块都有测试覆盖。"

---

## Quick Reference

| 项目 | 数据 |
|------|------|
| Tasks | 30 (Easy 10 / Medium 12 / Hard 8) |
| TSR | 90% |
| Test Pass Rate | 96.6% |
| Security Block Rate | 100% |
| Unit Tests | 311 |
| Tools | 6 |
| Metrics | 7 advanced |
| Error Types | 7 |
| Demo Scenarios | 3 |

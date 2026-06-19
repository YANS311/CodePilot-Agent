# CodePilot Agent — 在线项目简介 (BOSS直聘 / 简历)

## 项目名称
CodePilot Agent — 轻量级智能编程助手

## 项目定位
从零构建的 **ReAct Agent** + **Tool Calling** 编程助手，能自主定位 bug、读写代码、运行测试、生成 diff，支持 30 个评测任务，TSR 达 90%。

## 技术栈
Python 3.11+ / FastAPI / Pydantic Settings / OpenAI Compatible API / Docker (可选)

## 核心架构

```
User Prompt → ReAct Agent Loop (Think → Act → Observe)
                  ↓
            Tool Calling (search_code / read_file / write_file / run_tests / git_diff / git_status)
                  ↓
            Language Detector → PythonAdapter (full) / Java / Node (stubs)
                  ↓
            Execution Runner (Local subprocess / Docker sandbox)
```

## 核心功能

| 功能模块 | 技术实现 |
|:---------|:---------|
| ReAct Agent | Think-Act-Observe 循环 + OpenAI Function Calling |
| 6 工具 | search_code / read_file / write_file / run_tests / git_diff / git_status |
| Language Adapter | BaseLanguageAdapter ABC + PythonAdapter (完整), Java/Node (stub) |
| 安全防护 | 6 类风险检测 (Secret/System/Destructive/Injection/Excessive/Exfiltration) |
| 评测框架 | 30 任务, 7 项高级指标, 错误归因, Markdown 报告 |
| 前端 | 上传 workspace, 对话界面, 安全警告卡片 |

## 评测结果

| 指标 | 值 |
|:-----|:---|
| Task Success Rate (TSR) | 90.0% (27/30) |
| Test Pass Rate | 96.6% (85/88) |
| Security Block Rate | 100% (20/20) |
| Tool Call Validity | ~98% |
| Verification Completion | ~85% |
| Planning Efficiency | 6.9 avg tool calls/success |

## 难度分布

| 难度 | 任务数 | 通过率 |
|:-----|-------:|-------:|
| Easy | 10 | 100% |
| Medium | 12 | 92% |
| Hard | 8 | 75% |

## 技术亮点

1. **ReAct Agent Loop** — 实现完整的 Think-Act-Observe 循环，支持多轮推理
2. **Tool Calling** — 基于 OpenAI Function Calling 协议，6 个工具协同工作
3. **Language Adapter** — 抽象基类 + 策略模式，自动检测语言并调度执行
4. **Security Guardrails** — 6 类风险检测，100% 拦截率，20 个攻击样例验证
5. **Advanced Eval Metrics** — 参考 RAGAS 思想，定义 7 项 Coding Agent 专属指标
6. **Error Taxonomy** — 7 类错误自动归因，支持错误分析和改进
7. **Docker Sandbox** — 可选 Docker 隔离执行，支持 `--read-only --network none`

## 项目规模

| 指标 | 数值 |
|:-----|:-----|
| 源文件 | 40+ |
| 测试用例 | 192+ |
| 评测任务 | 30 |
| 攻击样例 | 20 |
| 开发周期 | D1-D15 (15 个迭代) |

## GitHub
https://github.com/YANS311/CodePilot-Agent

## 适用场景
- 面试展示：完整的 Agent 架构 + 评测体系
- 技术博客：ReAct Agent / Tool Calling / 安全防护 实战
- 开源贡献：轻量级 Coding Agent 参考实现

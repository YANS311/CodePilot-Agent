# CodePilot Agent

轻量级 Python Coding Agent，基于 ReAct 循环 + OpenAI Function Calling 实现单 Agent 编码辅助。

## 核心能力

- **ReAct Agent Loop** — Think → Act → Observe 循环驱动
- **Tool Calling** — 基于 OpenAI Function Calling 协议的工具调用
- **6 个内置工具** — search_code / read_file / write_file / run_tests / git_diff / git_status
- **Prompt Guardrail** — 检测伪造工具调用并自动纠正
- **Execution Environment** — 支持 Local / Docker 两种执行模式
- **Evaluation Framework** — 30 个评测任务，自动计算 TSR / Pass@1 等指标

## 技术栈

- Python 3.11+
- FastAPI
- Pydantic / Pydantic Settings
- OpenAI Compatible API (GPT-4o / DeepSeek / 本地模型)
- Docker (可选，沙箱执行)

## 快速启动

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 填入你的 API Key

# 3. 启动服务
uvicorn app.main:app --reload

# 4. 验证
curl http://localhost:8000/health
# {"status":"ok"}
```

## 运行测试

```bash
pip install pytest httpx
pytest tests/ -v
```

## 运行评测

```bash
# 全部 30 个任务
python scripts/run_eval.py

# 指定任务
python scripts/run_eval.py --tasks fix-subtract fix-divide-zero

# 报告输出到 reports/eval_report.md
```

## 项目结构

```
app/
├── main.py              # FastAPI 入口
├── core/
│   └── config.py        # 统一配置 (Pydantic Settings)
├── agent/
│   ├── react_agent.py   # ReAct Agent Loop
│   └── prompts.py       # System Prompt
├── tools/               # 6 个内置工具
│   ├── registry.py      # 工具注册中心
│   ├── search_code.py
│   ├── read_file.py
│   ├── write_file.py
│   ├── run_tests.py
│   ├── git_diff.py
│   └── git_status.py
├── execution/
│   ├── base.py          # Runner ABC
│   ├── local_runner.py  # 本地执行
│   ├── docker_runner.py # Docker 沙箱
│   └── factory.py       # Runner 工厂
└── evaluation/
    ├── schema.py        # EvalTask / EvalResult
    ├── runner.py        # 评测运行器
    ├── metrics.py       # 指标计算
    ├── analyzer.py      # 错误归因
    └── error_taxonomy.py # 错误分类

workspace/               # 工作区种子 (含 examples + tests)
evaluation/tasks.json    # 30 个评测任务定义
scripts/run_eval.py      # 评测 CLI
tests/                   # 147 个单元测试
```

## 评测指标

| 指标 | 说明 |
|------|------|
| TSR (Task Success Rate) | 任务成功率 |
| Pass@1 | 单次尝试成功率 |
| Tool Efficiency | 工具调用效率 |
| 任务按难度 | Easy / Medium / Hard 分组 |
| 错误分布 | 7 种错误类型自动归因 |

## License

MIT

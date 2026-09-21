---
name: repository-explorer
description: Analyze unfamiliar software repositories by identifying architecture, technology stack, entry points and execution call chains.
version: 1.0.0
tags:
  - repo-exploration
  - architecture-analysis
  - entrypoint-discovery
  - call-chain
  - codebase-understanding
---

# Procedural Knowledge: Repository Explorer & Codebase Onboarding

## Purpose
帮助 Agent 在接手陌生仓库或面对新代码库时，通过系统化、结构化的程序性知识快速建立清晰的代码认知，避免盲目搜索与无证据的幻觉推断。

---

## When to activate

当用户任务包含以下意图或关键词时激活该 Skill：

### 中文场景
- 分析代码库
- 梳理项目架构
- 找项目入口
- 分析调用链
- 接手项目

### 英文场景
- explore repository
- understand codebase
- find entry point
- trace execution flow

---

## Workflow

执行该 Skill 时，必须严格依序完成以下 4 个阶段（Phases），严禁跳步：

### Phase 1: Technology Stack Discovery (技术栈识别)
- **使用工具**：`read_file`
- **检查目标**：
  - Python 项目：`requirements.txt`, `pyproject.toml`, `Pipfile`, `setup.py`
  - Node.js 项目：`package.json`
  - 容器与部署：`Dockerfile`, `docker-compose.yml`
- **分析内容**：识别项目主编程语言版本、核心 Web/应用框架、持久化/ORM 库、关键外部组件依赖与打包运行环境。

### Phase 2: Architecture Discovery (架构与目录结构发现)
- **分析目标**：
  - 目录结构（Directory Structure）：通过目录扫描梳理顶层文件与目录分工。
  - 模块职责（Module Responsibility）：明确各核心子目录与模块的领域职责。
  - 架构风格（Architecture Pattern）：判断项目采用的架构模式（如 Controller-Service-Repository 经典分层架构、微内核插件架构、DDD 领域驱动或事件驱动架构）。

### Phase 3: Entry Point Discovery (入口定位)
- **分析目标**：定位系统与服务的真实启动入口和请求接入点。
- **关键特征检索**：
  - **Python**：
    - `FastAPI()` / `Flask()`
    - `main()` / `if __name__ == '__main__':`
    - `create_app()` 工厂函数
    - 命令行 CLI 入口（如 Click, Typer, argparse）
  - **Node.js**：
    - `package.json` 中的 `main`, `scripts.start`
    - `index.js`, `server.js`, `app.js`, `main.ts`

### Phase 4: Execution Flow Analysis (执行调用链跟踪)
- **分析目标**：追踪至少 1 条核心端到端业务链路（例如：HTTP Request → Router → Service → Storage/DB → Response）。
- **硬性约束（Evidence-based）**：
  - 每一步调用**必须**明确给出具体代码证据：
    1. `file path`（文件路径）
    2. `class/function`（类/函数名）
    3. `line number`（起始代码行号）
  - **严格禁止无证据的凭空推断与猜测**。

---

## Deliverables Template (输出模板)

Agent 完成分析后，必须严格遵循以下 Markdown 结构组织并交付最终报告：

# Project Overview
- 项目类型定位 (Web API / Microservice / CLI Tool / AI Agent / Library)
- 一句话核心业务功能概述

# Technology Stack
- 核心语言与运行时版本
- 核心开发框架与库
- 数据存储与持久化方案
- 构建工具与环境依赖

# Directory Architecture
| 目录/模块路径 | 架构分层 (Layer) | 核心职责与关键组件 |
| :--- | :--- | :--- |
| `path/to/module/` | 分层名称 | 职责简述 |

# Entry Points
- 主入口文件与代码锚点（文件路径 + 行号）
- 服务启动流程与生命周期钩子（如 lifespan / 启动事件）
- 启动命令示例

# Execution Flow
梳理典型端到端请求流（必须包含代码证据）：
1. **[步骤 1: 触发与路由]**: `file path` | `class/function` | `line number`
2. **[步骤 2: 鉴权与守卫]**: `file path` | `class/function` | `line number`
3. **[步骤 3: 业务层处理]**: `file path` | `class/function` | `line number`
4. **[步骤 4: 数据访问与持久化]**: `file path` | `class/function` | `line number`
5. **[步骤 5: 响应封装返回]**: `file path` | `class/function` | `line number`

# Extension Points
- 项目如何扩展新功能（如添加新 API Router、新 Tool、新 Plugin 或新 Middleware 的推荐方式）

# Risks
- 上手注意事项、环境陷阱、缺失的配置项（如环境变量、API Key、外部未就绪服务等）
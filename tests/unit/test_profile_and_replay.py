from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agent.react_agent import ReActAgent
from app.core.kernel.context import AgentContext
from app.core.kernel.events import EventBus, KernelEvent
from app.core.kernel.profile import PluginConfig, ProfileLoader, ProfileSpec
from app.core.kernel.replayer import EventStreamReplayer


@pytest.fixture
def sample_profile_yaml(tmp_path: Path) -> Path:
    yaml_content = """
profile:
  name: "test-coding-profile"
  version: "1.0.0"
  description: "Test Profile for Unit Verification"

plugins:
  - name: "model_adapter"
    config:
      model: "gpt-4o"
      ci_mode: true
  - name: "native_tools"
  - name: "guardrails"
  - name: "react_orchestrator"
    config:
      workspace_root: "./workspace"
      max_tool_calls: 5
"""
    file_path = tmp_path / "test_profile.yaml"
    file_path.write_text(yaml_content, encoding="utf-8")
    return file_path


class TestProfileLoader:
    def test_load_from_yaml(self, sample_profile_yaml: Path):
        spec = ProfileLoader.load_from_yaml(sample_profile_yaml)
        assert spec.name == "test-coding-profile"
        assert spec.version == "1.0.0"
        assert len(spec.plugins) == 4
        assert spec.plugins[0].name == "model_adapter"

    def test_bootstrap_complete_system(self, sample_profile_yaml: Path):
        async def _run():
            ctx = AgentContext()
            manager = await ProfileLoader.bootstrap(sample_profile_yaml, context=ctx)

            # 验证所有服务是否按依赖注入成功
            assert ctx.inject("llm_client") is not None
            assert ctx.inject("tool_registry") is not None
            assert ctx.inject("guardrail") is not None

            agent = ctx.inject_typed("agent", ReActAgent)
            assert agent._max_tool_calls == 5

            # 验证可逆生命周期
            await manager.deactivate_all()
            with pytest.raises(KeyError):
                ctx.inject("agent")

        asyncio.run(_run())

    def test_load_built_in_profiles(self):
        coding_spec = ProfileLoader.load_from_yaml(PROJECT_ROOT / "profiles" / "coding.yaml")
        assert coding_spec.name == "codepilot-coding"
        assert len(coding_spec.plugins) == 5

        eval_spec = ProfileLoader.load_from_yaml(PROJECT_ROOT / "profiles" / "headless_eval.yaml")
        assert eval_spec.name == "codepilot-eval"
        assert len(eval_spec.plugins) == 4


class TestEventStreamReplayer:
    def test_event_export_and_import(self, tmp_path: Path):
        events = [
            KernelEvent(type="task:start", payload={"task_id": "T01"}),
            KernelEvent(type="tool:call", payload={"tool": "search_code", "query": "add"}),
            KernelEvent(type="task:finish", payload={"success": True}),
        ]
        replayer = EventStreamReplayer(events)
        output_file = tmp_path / "trajectory.jsonl"
        replayer.export_jsonl(output_file)

        assert output_file.exists()

        # 重新导入
        restored_replayer = EventStreamReplayer.from_jsonl(output_file)
        assert len(restored_replayer._events) == 3
        assert restored_replayer._events[1].payload["tool"] == "search_code"

    def test_replay_to_bus(self):
        async def _run():
            events = [
                KernelEvent(type="step", payload={"step": 1}),
                KernelEvent(type="step", payload={"step": 2}),
                KernelEvent(type="step", payload={"step": 3}),
            ]
            replayer = EventStreamReplayer(events)
            bus = EventBus()
            received = []

            bus.on("step", lambda e: received.append(e.payload["step"]))
            replayed_count = await replayer.replay_to_bus(bus, up_to_step=2)

            assert replayed_count == 2
            assert received == [1, 2]

        asyncio.run(_run())

    def test_fork_at_step(self):
        events = [
            KernelEvent(type="init", payload={}),
            KernelEvent(type="step_1", payload={"action": "edit"}),
            KernelEvent(type="step_2_failed", payload={"error": "test_failed"}),
        ]
        replayer = EventStreamReplayer(events)

        # 在第 2 步（即失败前）进行分叉
        forked_ctx = replayer.fork_at(2)
        assert len(forked_ctx.events.get_events()) == 2
        assert forked_ctx.events.get_events()[-1].type == "step_1"

    def test_fork_out_of_range(self):
        replayer = EventStreamReplayer([])
        with pytest.raises(IndexError):
            replayer.fork_at(5)

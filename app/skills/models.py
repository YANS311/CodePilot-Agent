"""app/skills/models.py — Agent Skills 数据模型与契约定义。

强调：
Tool = Agent 能执行什么操作 (Capabilities / Actions)
Skill = Agent 完成某类任务应遵循的工作流与程序性知识 (Procedural Knowledge)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class SkillMetadata:
    """Skill 级别 1 (Level 1) 元数据信息，用于快速检索与轻量注入。"""

    name: str
    description: str
    path: str
    tags: List[str] = field(default_factory=list)
    version: str = "1.0.0"

    def to_summary(self) -> str:
        """生成 Level 1 简要摘要。"""
        return f"- **{self.name}**: {self.description}"


@dataclass
class Skill:
    """完整 Skill 实例，包含 Level 2 操作指引与 Level 3 资源。"""

    metadata: SkillMetadata
    instructions: str
    references: Dict[str, str] = field(default_factory=dict)
    scripts: Dict[str, str] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.metadata.name

    @property
    def description(self) -> str:
        return self.metadata.description

    def to_prompt_instruction(self) -> str:
        """生成注入到 Agent Prompt 中的 Level 2/3 程序性工作流指导与可用资源。"""
        sections = [
            f"\n\n--- [Active Skill: {self.name}] ---",
            f"Description: {self.description}\n",
            "### Procedural Workflow Guidelines:",
            self.instructions.strip(),
        ]

        # Level 3: Available helper scripts
        if self.scripts:
            sections.append("\n### Available Helper Scripts (Executable via bash_runner / python):")
            skill_dir = Path(self.metadata.path).parent
            for script_name in sorted(self.scripts.keys()):
                script_path = (skill_dir / "scripts" / script_name).as_posix()
                sections.append(f"- `{script_path}`: Helper tool for {self.name}.")

        # Level 3: Available domain references
        if self.references:
            sections.append("\n### Available Domain References (Readable via read_file):")
            skill_dir = Path(self.metadata.path).parent
            for ref_name in sorted(self.references.keys()):
                ref_path = (skill_dir / "references" / ref_name).as_posix()
                sections.append(f"- `{ref_path}`: Reference documentation.")

        sections.append(f"--- [End Skill: {self.name}] ---\n")
        return "\n".join(sections)

"""app/skills/loader.py — Skill 文件扫描与三级渐进式加载器 (Progressive Disclosure)。

Level 1 (Metadata): 启动时仅扫描 frontmatter 生成摘要元数据，零 Prompt 污染。
Level 2 (Instructions): 任务匹配后按需加载 SKILL.md 正文指引。
Level 3 (Resources): 仅在显式需要时读取 references/ 与 scripts/ 资源。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import yaml

from app.skills.models import Skill, SkillMetadata

logger = logging.getLogger(__name__)


class SkillLoader:
    """Skill 规范加载器。"""

    @staticmethod
    def parse_frontmatter(content: str) -> Tuple[Dict[str, Any], str]:
        """解析 SKILL.md 顶部的 YAML Frontmatter。
        
        格式示例:
        ---
        name: bug-fix
        description: Diagnose and fix reproducible software defects.
        tags: [debugging, pytest]
        ---
        # Instructions
        ...
        """
        lines = content.splitlines()
        if not lines or lines[0].strip() != "---":
            return {}, content

        frontmatter_lines: List[str] = []
        body_lines: List[str] = []
        in_frontmatter = True

        for line in lines[1:]:
            if in_frontmatter:
                if line.strip() == "---":
                    in_frontmatter = False
                else:
                    frontmatter_lines.append(line)
            else:
                body_lines.append(line)

        if in_frontmatter:
            # 格式不合规 (未闭合的 ---)，回退为全文正文
            return {}, content

        try:
            metadata_dict = yaml.safe_load("\n".join(frontmatter_lines)) or {}
            if not isinstance(metadata_dict, dict):
                metadata_dict = {}
        except Exception as exc:
            logger.warning("Failed to parse YAML frontmatter: %s", exc)
            metadata_dict = {}

        return metadata_dict, "\n".join(body_lines)

    @classmethod
    def scan_skills(cls, skills_dir: str | Path) -> Dict[str, SkillMetadata]:
        """扫描技能根目录，仅加载 Level 1 元数据。"""
        dir_path = Path(skills_dir)
        metadata_map: Dict[str, SkillMetadata] = {}

        if not dir_path.exists() or not dir_path.is_dir():
            logger.debug("Skills directory '%s' does not exist", skills_dir)
            return metadata_map

        for item in dir_path.iterdir():
            if not item.is_dir():
                continue
            skill_file = item / "SKILL.md"
            if not skill_file.exists():
                continue

            try:
                content = skill_file.read_text(encoding="utf-8")
                frontmatter, _ = cls.parse_frontmatter(content)
                name = frontmatter.get("name", item.name)
                description = frontmatter.get("description", f"Procedural skill for {name}")
                tags = frontmatter.get("tags", [])
                if isinstance(tags, str):
                    tags = [tags]
                version = str(frontmatter.get("version", "1.0.0"))

                metadata = SkillMetadata(
                    name=name,
                    description=description,
                    path=str(skill_file.resolve()),
                    tags=tags,
                    version=version,
                )
                metadata_map[name] = metadata
            except Exception as exc:
                logger.warning("Failed to scan skill in '%s': %s", item, exc)

        return metadata_map

    @classmethod
    def load_skill_body(cls, skill_metadata: SkillMetadata) -> Optional[Skill]:
        """按需加载 Level 2 Instructions 与关联资源。"""
        skill_file = Path(skill_metadata.path)
        if not skill_file.exists():
            return None

        content = skill_file.read_text(encoding="utf-8")
        _, body = cls.parse_frontmatter(content)

        # 扫描 Level 3 resources (references / scripts)
        skill_dir = skill_file.parent
        references: Dict[str, str] = {}
        scripts: Dict[str, str] = {}

        ref_dir = skill_dir / "references"
        if ref_dir.exists() and ref_dir.is_dir():
            for ref_file in ref_dir.glob("*"):
                if ref_file.is_file():
                    try:
                        references[ref_file.name] = ref_file.read_text(encoding="utf-8")
                    except Exception:
                        pass

        script_dir = skill_dir / "scripts"
        if script_dir.exists() and script_dir.is_dir():
            for script_file in script_dir.glob("*"):
                if script_file.is_file():
                    try:
                        scripts[script_file.name] = script_file.read_text(encoding="utf-8")
                    except Exception:
                        pass

        return Skill(
            metadata=skill_metadata,
            instructions=body,
            references=references,
            scripts=scripts,
        )

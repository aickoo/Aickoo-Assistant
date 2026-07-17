#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@Project:    Aickoo-Assistant
@Author:     艾可科技（昆山）有限责任公司
@Contact:    aickoo@163.com
@CreateTime: 2026-07-07
@Copyright:  Copyright (c) 2026 艾可科技（昆山）有限责任公司
@License:    All Rights Reserved.
"""


from __future__ import annotations
import os
import re
import threading
from pathlib import Path
from typing import List, Dict, Optional, Callable, Any
from dataclasses import dataclass, field
from enum import Enum
import yaml
from aickoo.internal.util.utils import get_skills_path

# ============================================================================
# 示例 SKILL.md 模板
# ============================================================================

SKILL_MD_TEMPLATE = '''---
name: example-skill
description: A brief description of what this skill does
triggers:
  keywords:
    - keyword1
    - keyword2
  patterns:
    - "pattern.*regex"
tools:
  - bash
  - grep
priority: high
mcp: []
---

# Example Skill

This is the full skill instruction that will be loaded when the skill is invoked.

## Capabilities
- Capability 1
- Capability 2

## Best Practices
1. Practice 1
2. Practice 2

## Examples
```bash
# Example command
``'
'''


class SkillPriority(Enum):
    """Skill 优先级"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class SkillTrigger:
    """Skill 触发条件"""
    keywords: List[str] = field(default_factory=list)
    patterns: List[str] = field(default_factory=list)


@dataclass
class SkillMatch:
    """技能匹配结果"""
    skill: Skill
    matched_keywords: List[str]
    match_score: float  # 匹配得分，用于排序


@dataclass
class SkillMeta:
    """Skill 元数据 (YAML frontmatter)"""
    name: str = ""
    description: str = ""
    triggers: SkillTrigger = field(default_factory=SkillTrigger)
    tools: List[str] = field(default_factory=list)
    priority: SkillPriority = SkillPriority.MEDIUM
    mcp: List[str] = field(default_factory=list)  # 需要的 MCP servers

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SkillMeta:
        """从字典创建 SkillMeta"""
        triggers_data = data.get("triggers", {})
        triggers = SkillTrigger(
            keywords=triggers_data.get("keywords", []),
            patterns=triggers_data.get("patterns", [])
        )

        priority_str = data.get("priority", "medium").lower()
        priority = SkillPriority(priority_str) if priority_str in [p.value for p in SkillPriority] else SkillPriority.MEDIUM

        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            triggers=triggers,
            tools=data.get("tools", []),
            priority=priority,
            mcp=data.get("mcp", [])
        )


@dataclass
class Skill:
    """完整的 Skill 结构"""
    meta: SkillMeta
    content: str  # 完整的 skill 指令内容
    file_path: str = ""
    base_path: str = ""
    source: str = "unknown"  # "user", "project", "builtin"

    def to_description(self) -> str:
        """生成用于 Prompt 注入的简短描述"""
        return f"- **{self.meta.name}**: {self.meta.description}"

    def to_full_prompt(self) -> str:
        """生成完整的 skill prompt"""
        return f"""# Skill: {self.meta.name}

{self.content}

## Required Tools
{', '.join(self.meta.tools) if self.meta.tools else 'None specified'}
"""


class SkillParser:
    """SKILL.md 文件解析器"""

    # YAML frontmatter 正则模式
    FRONTMATTER_PATTERN = re.compile(r'^---\s*\n(.*?)\n---\s*\n(.*)$', re.DOTALL)

    @classmethod
    def parse_file(cls, file_path: str) -> Optional[Skill]:
        """解析 SKILL.md 文件"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return cls.parse_content(content, file_path)
        except Exception as e:
            print(f"[SkillParser] Error parsing {file_path}: {e}")
            return None

    @classmethod
    def parse_content(cls, content: str, file_path: str = "") -> Optional[Skill]:
        """解析 SKILL.md 内容"""
        match = cls.FRONTMATTER_PATTERN.match(content)
        if not match:
            print(f"[SkillParser] Invalid SKILL.md format: missing frontmatter")
            return None

        yaml_content = match.group(1)
        body_content = match.group(2).strip()

        try:
            meta_dict = yaml.safe_load(yaml_content)
            if not isinstance(meta_dict, dict):
                print(f"[SkillParser] Invalid YAML frontmatter")
                return None

            meta = SkillMeta.from_dict(meta_dict)
            if not meta.name:
                # 使用文件夹名作为默认名称
                if file_path:
                    meta.name = os.path.basename(os.path.dirname(file_path))
                else:
                    meta.name = "unnamed-skill"

            return Skill(
                meta=meta,
                content=body_content,
                file_path=file_path,
                base_path=os.path.dirname(file_path)
            )
        except yaml.YAMLError as e:
            print(f"[SkillParser] YAML parse error: {e}")
            return None


class SkillRegistry:
    """
    Skill 注册表 - 单例模式

    负责:
    1. 从多个目录扫描和加载 Skills
    2. 维护技能索引
    3. 根据用户输入匹配相关技能
    4. 生成用于 Prompt 注入的技能描述
    """

    _instance: Optional[SkillRegistry] = None
    _lock = threading.Lock()

    def __new__(cls) -> SkillRegistry:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self._skills: Dict[str, Skill] = {}
        self._keyword_index: Dict[str, List[str]] = {}  # keyword -> skill names
        self._pattern_index: List[tuple] = []  # [(pattern, skill_name), ...]
        self._mu = threading.RLock()

        # 加载路径配置
        self._builtin_dir: Optional[str] = None
        self._user_dir: Optional[str] = None
        self._project_dir: Optional[str] = None

    @classmethod
    def get_instance(cls) -> SkillRegistry:
        """获取单例实例"""
        return cls()

    def configure(
            self,
            builtin_dir: Optional[str] = None,
            user_dir: Optional[str] = None,
            project_dir: Optional[str] = None
    ) -> None:
        """配置加载路径"""
        self._builtin_dir = builtin_dir
        self._user_dir = user_dir
        self._project_dir = project_dir

    def load_all(self) -> int:
        """
        从所有配置的目录加载 Skills

        Returns:
            加载的 skill 数量
        """
        total_loaded = 0

        # 1. 加载内置 skills (优先级最低，可被覆盖)
        if self._builtin_dir:
            total_loaded += self._load_from_dir(self._builtin_dir, "builtin")

        # 2. 加载用户 skills
        if self._user_dir:
            total_loaded += self._load_from_dir(self._user_dir, "user")

        # 3. 加载项目 skills (优先级最高)
        if self._project_dir:
            total_loaded += self._load_from_dir(self._project_dir, "project")

        # 自动发现用户目录
        if not self._user_dir:
            home = os.environ.get("HOME") or os.environ.get("USERPROFILE")
            if home:
                default_user_dir = os.path.join(home, ".config", "aickoo", "skills")
                if os.path.isdir(default_user_dir):
                    total_loaded += self._load_from_dir(default_user_dir, "user")

        # 构建索引
        self._build_indices()

        return total_loaded

    def _load_from_dir(self, directory: str, source: str) -> int:
        """
        从指定目录加载 Skills

        目录结构预期:
        skills/
        ├── git-master/
        │   └── SKILL.md
        ├── playwright/
        │   └── SKILL.md

        Args:
            directory: skills 目录路径
            source: 来源标识 ("builtin", "user", "project")

        Returns:
            加载的 skill 数量
        """
        if not os.path.isdir(directory):
            print(f"[SkillRegistry] Directory not found: {directory}")
            return 0

        loaded = 0

        # 遍历目录，查找 SKILL.md 文件
        for item in os.listdir(directory):
            item_path = os.path.join(directory, item)

            # 跳过非目录
            if not os.path.isdir(item_path):
                continue

            # 查找 SKILL.md
            skill_file = os.path.join(item_path, "SKILL.md")
            if not os.path.isfile(skill_file):
                # 也尝试小写
                skill_file = os.path.join(item_path, "skill.md")
                if not os.path.isfile(skill_file):
                    continue

            # 解析 skill
            skill = SkillParser.parse_file(skill_file)
            if skill:
                skill.source = source
                with self._mu:
                    self._skills[skill.meta.name] = skill
                loaded += 1
                print(f"[SkillRegistry] Loaded skill: {skill.meta.name} (from {source})")

        return loaded

    def _build_indices(self) -> None:
        """构建关键词和模式索引"""
        with self._mu:
            # 清空旧索引
            self._keyword_index.clear()
            self._pattern_index.clear()

            # 构建新索引
            for name, skill in self._skills.items():
                # 关键词索引
                for keyword in skill.meta.triggers.keywords:
                    keyword_lower = keyword.lower()
                    if keyword_lower not in self._keyword_index:
                        self._keyword_index[keyword_lower] = []
                    self._keyword_index[keyword_lower].append(name)

                # 模式索引
                for pattern in skill.meta.triggers.patterns:
                    try:
                        compiled = re.compile(pattern, re.IGNORECASE)
                        self._pattern_index.append((compiled, name))
                    except re.error as e:
                        print(f"[SkillRegistry] Invalid pattern in {name}: {pattern} - {e}")

    def get(self, name: str) -> Optional[Skill]:
        """根据名称获取 Skill"""
        with self._mu:
            return self._skills.get(name)

    def get_all(self) -> List[Skill]:
        """获取所有 Skills"""
        with self._mu:
            return list(self._skills.values())

    def get_names(self) -> List[str]:
        """获取所有 Skill 名称"""
        with self._mu:
            return list(self._skills.keys())

    def match_skills(self, user_input: str) -> List[SkillMatch]:
        """
        根据用户输入匹配相关的 Skills

        Args:
            user_input: 用户输入文本

        Returns:
            匹配结果列表，按得分排序
        """
        matches: Dict[str, SkillMatch] = {}
        input_lower = user_input.lower()

        with self._mu:
            # 1. 关键词匹配
            for keyword, skill_names in self._keyword_index.items():
                if keyword in input_lower:
                    for skill_name in skill_names:
                        skill = self._skills.get(skill_name)
                        if skill:
                            if skill_name not in matches:
                                matches[skill_name] = SkillMatch(
                                    skill=skill,
                                    matched_keywords=[],
                                    match_score=0.0
                                )
                            matches[skill_name].matched_keywords.append(keyword)

            # 2. 正则模式匹配
            for pattern, skill_name in self._pattern_index:
                if pattern.search(user_input):
                    skill = self._skills.get(skill_name)
                    if skill:
                        if skill_name not in matches:
                            matches[skill_name] = SkillMatch(
                                skill=skill,
                                matched_keywords=[],
                                match_score=0.0
                            )

        # 计算得分
        for match in matches.values():
            # 基础得分：匹配的关键词数量
            match.match_score = len(match.matched_keywords) * 1.0

            # 优先级加成
            if match.skill.meta.priority == SkillPriority.HIGH:
                match.match_score += 2.0
            elif match.skill.meta.priority == SkillPriority.MEDIUM:
                match.match_score += 1.0

        # 按得分排序
        return sorted(matches.values(), key=lambda m: m.match_score, reverse=True)

    def get_skills_description(self) -> str:
        """
        生成用于注入到 System Prompt 的 Skills 描述

        Returns:
            Markdown 格式的 skills 列表
        """
        with self._mu:
            if not self._skills:
                return ""

            lines = [
                "",
                "# Available Skills",
                "",
                "You have access to the following skills. Use the `skill` tool to load and invoke them:",
                "",
            ]

            # 按优先级和名称排序
            sorted_skills = sorted(
                self._skills.values(),
                key=lambda s: (
                    -{"high": 0, "medium": 1, "low": 2}.get(s.meta.priority.value, 1),
                    s.meta.name
                )
            )

            for skill in sorted_skills:
                lines.append(skill.to_description())

            lines.append("")
            lines.append("To use a skill, call: `skill(name=\"skill-name\", action=\"load\")`")
            lines.append("")

            return "\n".join(lines)

    def get_skills_for_context(self, max_skills: int = 5) -> str:
        """
        获取用于上下文注入的简化描述

        当 skills 数量很多时，只注入最相关的描述

        Args:
            max_skills: 最大注入数量

        Returns:
            简化的 skills 描述
        """
        with self._mu:
            if not self._skills:
                return ""

            # 只返回高优先级的 skills
            high_priority = [
                s for s in self._skills.values()
                if s.meta.priority == SkillPriority.HIGH
            ]

            if len(high_priority) > max_skills:
                high_priority = high_priority[:max_skills]

            if not high_priority:
                return ""

            lines = ["Available skills (use `skill` tool):"]
            for s in high_priority:
                lines.append(f"  - {s.meta.name}: {s.meta.description}")

            return "\n".join(lines)

    def register_skill(self, skill: Skill) -> None:
        """手动注册一个 Skill"""
        with self._mu:
            self._skills[skill.meta.name] = skill

            # 更新索引
            for keyword in skill.meta.triggers.keywords:
                keyword_lower = keyword.lower()
                if keyword_lower not in self._keyword_index:
                    self._keyword_index[keyword_lower] = []
                if skill.meta.name not in self._keyword_index[keyword_lower]:
                    self._keyword_index[keyword_lower].append(skill.meta.name)

            for pattern in skill.meta.triggers.patterns:
                try:
                    compiled = re.compile(pattern, re.IGNORECASE)
                    self._pattern_index.append((compiled, skill.meta.name))
                except re.error:
                    pass

    def unregister_skill(self, name: str) -> bool:
        """注销一个 Skill"""
        with self._mu:
            if name in self._skills:
                del self._skills[name]
                # 重建索引
                self._build_indices()
                return True
            return False

    def clear(self) -> None:
        """清空所有 Skills"""
        with self._mu:
            self._skills.clear()
            self._keyword_index.clear()
            self._pattern_index.clear()

    def stats(self) -> Dict[str, Any]:
        """获取注册表统计信息"""
        with self._mu:
            sources = {}
            for skill in self._skills.values():
                sources[skill.source] = sources.get(skill.source, 0) + 1

            return {
                "total_skills": len(self._skills),
                "by_source": sources,
                "total_keywords": len(self._keyword_index),
                "total_patterns": len(self._pattern_index)
            }


# ============================================================================
# 便捷函数
# ============================================================================

def get_registry() -> SkillRegistry:
    """获取全局 Skill Registry 实例"""
    return SkillRegistry.get_instance()


def load_skills(project_dir: Optional[str] = None) -> int:
    """
    加载所有 Skills 的便捷函数

    Args:
        project_dir: 项目目录，用于加载项目级 skills

    Returns:
        加载的 skill 数量
    """
    registry = get_registry()

    if project_dir:
        registry.configure(project_dir=os.path.join(project_dir, ".aickoo", "skills"))

    return registry.load_all()


class SkillFactory:
    registry = None

    @staticmethod
    def get_skill_registry() -> SkillRegistry:
        # init
        if SkillFactory.registry is None:
            SkillFactory.registry = SkillRegistry.get_instance()

            # 配置测试目录
            # test_dir = os.path.join("D:\\workspace_python\\python-aickoo", "skills")
            test_dir = get_skills_path()

            # 加载
            SkillFactory.registry.configure(project_dir=test_dir)
            loaded_num = SkillFactory.registry.load_all()

        return SkillFactory.registry

    @staticmethod
    def get_all_skills() -> List[Skill]:
        SkillFactory.registry = SkillFactory.get_skill_registry()
        return SkillFactory.registry.get_all()

    @staticmethod
    def get_skill(name: str) -> List[Skill]:
        SkillFactory.registry = SkillFactory.get_skill_registry()
        return SkillFactory.registry.get(name)


if __name__ == "__main__":
    # 测试 Registry
    registry = SkillRegistry.get_instance()

    # 配置测试目录
    test_dir = os.path.join("D:\\workspace_python\\Aickoo-Assistant", "skills")

    # test_dir = os.path.join(os.path.dirname(__file__), "skills")
    #     os.makedirs(test_dir, exist_ok=True)
    #
    #     # 创建测试 skill
    #     test_skill_dir = os.path.join(test_dir, "delete-skill")
    #     os.makedirs(test_skill_dir, exist_ok=True)
    #
    #     with open(os.path.join(test_skill_dir, "SKILL.md"), "w") as f:
    #         f.write("""---
    # name: delete-skill
    # description: A delete skill for testing
    # triggers:
    #   keywords:
    #     - delete
    #     - testing
    # tools:
    #   - bash
    # priority: high
    # ---
    #
    # # Test Skill
    #
    # This is a delete skill for testing the registry.
    # """)

    # 加载
    registry.configure(project_dir=test_dir)
    loaded = registry.load_all()
    print(f"Loaded {loaded} skills")

    # 统计
    print(f"Stats: {registry.stats()}")

    # 匹配测试
    matches = registry.match_skills("docx")
    print(f"\nMatches for 'docx':")
    for m in matches:
        print(f"  - {m.skill.meta.name} (score: {m.match_score})")

    # 描述
    print(f"\nSkills Description:\n{registry.get_skills_description()}")

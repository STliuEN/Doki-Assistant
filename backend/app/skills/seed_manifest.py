"""Immutable import descriptors for Doki's built-in standard Skill seeds.

Seed packages are not trusted runtime plugins. Callers must submit every
``package_source`` to the same Skill package validator and storage/import
pipeline used for third-party packages. This manifest grants no execution,
dependency-installation, filesystem, network, or secret access.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

RoutingExamples = tuple[tuple[Literal["positive", "negative"], tuple[str, ...]], ...]

SEED_PACKAGES_DIR = Path(__file__).resolve().parent / "seed_packages"
_PACKAGE_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_LEGACY_ALIAS_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


@dataclass(frozen=True, slots=True)
class SeedSkillManifest:
    package_name: str
    package_source: Path
    legacy_alias: str
    display_name: str
    tool_ids: tuple[str, ...]
    default: bool
    visibility: str
    order: int
    always_on: bool
    routable: bool
    routing_examples: RoutingExamples

    def __post_init__(self) -> None:
        if not _PACKAGE_NAME_PATTERN.fullmatch(self.package_name):
            raise ValueError(f"invalid seed package name: {self.package_name}")
        if not _LEGACY_ALIAS_PATTERN.fullmatch(self.legacy_alias):
            raise ValueError(f"invalid legacy Skill alias: {self.legacy_alias}")
        expected_source = SEED_PACKAGES_DIR / self.package_name
        if self.package_source != expected_source:
            raise ValueError(f"seed source must be {expected_source}")
        kinds = tuple(kind for kind, _ in self.routing_examples)
        if len(kinds) != len(set(kinds)):
            raise ValueError(f"duplicate routing example kind for {self.package_name}")

    @property
    def source_path(self) -> Path:
        """Explicit package path to pass to the common validation/import flow."""

        return self.package_source


def _source(package_name: str) -> Path:
    return SEED_PACKAGES_DIR / package_name


SEED_SKILL_MANIFEST: tuple[SeedSkillManifest, ...] = (
    SeedSkillManifest(
        package_name="knowledge-research",
        package_source=_source("knowledge-research"),
        legacy_alias="knowledge_research",
        display_name="知识库问答",
        tool_ids=("rag_summary",),
        default=True,
        visibility="public",
        order=20,
        always_on=False,
        routable=True,
        routing_examples=(("positive", ("根据上传文档总结要点", "这份资料讲了什么", "从知识库里查找相关内容")),),
    ),
    SeedSkillManifest(
        package_name="mcp-smoke-test",
        package_source=_source("mcp-smoke-test"),
        legacy_alias="mcp_smoke_test",
        display_name="MCP 连通性测试",
        tool_ids=("mcp_powershell_ls_test_list_project_files",),
        default=True,
        visibility="public",
        order=90,
        always_on=False,
        routable=True,
        routing_examples=(("positive", ("测试 MCP 工具是否连通", "做一次 MCP 冒烟测试", "验证外部工具发现和调用")),),
    ),
    SeedSkillManifest(
        package_name="memory-cleanup",
        package_source=_source("memory-cleanup"),
        legacy_alias="memory_cleanup",
        display_name="记忆事项·清理（归档/删除）",
        tool_ids=("current_time", "list_memories", "get_memory", "archive_memory", "delete_memory"),
        default=False,
        visibility="public",
        order=52,
        always_on=False,
        routable=True,
        routing_examples=(("positive", ("删除昨天那条事项", "归档已经不需要的提醒", "清除这个待办")),),
    ),
    SeedSkillManifest(
        package_name="memory-read",
        package_source=_source("memory-read"),
        legacy_alias="memory_read",
        display_name="记忆事项·查询",
        tool_ids=("current_time", "list_memories", "get_memory"),
        default=True,
        visibility="public",
        order=51,
        always_on=False,
        routable=True,
        routing_examples=(("positive", ("查一下今天的待办", "列出我的提醒清单", "看看这条事项详情")),),
    ),
    SeedSkillManifest(
        package_name="memory-write",
        package_source=_source("memory-write"),
        legacy_alias="memory_write",
        display_name="记忆事项·记录与变更",
        tool_ids=(
            "current_time",
            "create_memory",
            "list_memories",
            "get_memory",
            "update_memory",
            "complete_memory",
            "postpone_memory",
        ),
        default=True,
        visibility="public",
        order=50,
        always_on=False,
        routable=True,
        routing_examples=(("positive", ("帮我记一下明天开会", "新建一个待办事项", "把这个提醒延期到周五")),),
    ),
    SeedSkillManifest(
        package_name="note-research",
        package_source=_source("note-research"),
        legacy_alias="note_research",
        display_name="笔记检索",
        tool_ids=("search_notes", "note_stats", "related_notes"),
        default=True,
        visibility="public",
        order=30,
        always_on=False,
        routable=True,
        routing_examples=(("positive", ("搜索我以前写过的笔记", "查找相关笔记", "看看笔记统计")),),
    ),
    SeedSkillManifest(
        package_name="note-writer",
        package_source=_source("note-writer"),
        legacy_alias="note_writer",
        display_name="笔记写入",
        tool_ids=("create_note", "search_notes"),
        default=True,
        visibility="public",
        order=40,
        always_on=False,
        routable=True,
        routing_examples=(("positive", ("把这段内容创建成新笔记", "保存为一篇笔记", "在对话中写一条笔记")),),
    ),
    SeedSkillManifest(
        package_name="public-info-lookup",
        package_source=_source("public-info-lookup"),
        legacy_alias="public_info_lookup",
        display_name="外部信息查询",
        tool_ids=("mcp_public_info_lookup_query_university_info", "mcp_public_info_lookup_ping_check"),
        default=False,
        visibility="public",
        order=95,
        always_on=False,
        routable=True,
        routing_examples=(("positive", ("查询武汉大学公开资料", "ping example.com", "检测 8.8.8.8 端口连通性")),),
    ),
    SeedSkillManifest(
        package_name="review-planner",
        package_source=_source("review-planner"),
        legacy_alias="review_planner",
        display_name="复习计划",
        tool_ids=(
            "current_time",
            "today_reviews",
            "list_memories",
            "get_memory",
            "mark_memory_reviewed",
            "postpone_memory",
            "generate_review_question",
        ),
        default=True,
        visibility="public",
        order=60,
        always_on=False,
        routable=True,
        routing_examples=(("positive", ("今天要复习什么", "给我出一道复习题", "标记这条记忆已复习")),),
    ),
    SeedSkillManifest(
        package_name="system-context",
        package_source=_source("system-context"),
        legacy_alias="system_context",
        display_name="系统上下文",
        tool_ids=("current_time", "user_info"),
        default=True,
        visibility="public",
        order=10,
        always_on=True,
        routable=True,
        routing_examples=(("positive", ("现在几点", "今天几号", "我是谁")),),
    ),
)

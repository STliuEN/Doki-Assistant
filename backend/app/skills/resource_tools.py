"""Read-only progressive-disclosure tools for selected standard Skill resources."""

from __future__ import annotations

import json
from pathlib import PurePosixPath

from langchain_core.tools import BaseTool, tool

from app.skills.registry import RuntimeSkill
from app.skills.storage import skill_package_storage

MAX_RUNTIME_RESOURCE_BYTES = 64 * 1024
MAX_RUNTIME_RESOURCE_CHARS = 16_000
_TEXT_SUFFIXES = {
    ".css",
    ".csv",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".mjs",
    ".py",
    ".sh",
    ".text",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}


def build_resource_tools(skills: list[RuntimeSkill]) -> list[BaseTool]:
    """Bind resource reads to immutable packages selected for one Agent run."""

    by_identifier: dict[str, RuntimeSkill] = {}
    for skill in skills:
        for identifier in (skill.id, skill.stable_id, skill.canonical_name, *skill.aliases):
            by_identifier[identifier] = skill

    @tool(
        "skill_list_resources",
        description=(
            "List files bundled with a selected Skill. Use this after a selected Skill's instructions "
            "refer to a reference or asset; it never lists arbitrary host files."
        ),
    )
    async def list_resources(skill_id: str) -> str:
        skill = by_identifier.get(skill_id)
        if skill is None:
            return "The requested Skill is not selected for this run."
        resources = [
            {
                "path": resource.path,
                "kind": resource.kind,
                "size": resource.size,
                "sha256": resource.sha256,
                "readable": PurePosixPath(resource.path).suffix.casefold() in _TEXT_SUFFIXES,
            }
            for resource in skill.resources
        ]
        return json.dumps(
            {"skill_id": skill.id, "version": skill.version_number, "digest": skill.digest, "resources": resources},
            ensure_ascii=False,
        )

    @tool(
        "skill_read_resource",
        description=(
            "Read one UTF-8 text resource from a selected Skill package by exact relative path. "
            "Binary files and arbitrary host paths are never returned, and package scripts are never executed."
        ),
    )
    async def read_resource(skill_id: str, path: str) -> str:
        skill = by_identifier.get(skill_id)
        if skill is None:
            return "The requested Skill is not selected for this run."
        resource = next((item for item in skill.resources if item.path == path), None)
        if resource is None:
            return "The requested resource does not exist in this immutable Skill version."
        if PurePosixPath(resource.path).suffix.casefold() not in _TEXT_SUFFIXES:
            return (
                f"Resource {resource.path} is binary or unsupported for prompt loading "
                f"(size={resource.size}, sha256={resource.sha256})."
            )
        try:
            content = skill_package_storage.read_resource(
                skill.storage_key,
                resource.path,
                max_bytes=MAX_RUNTIME_RESOURCE_BYTES,
                expected_digest=skill.digest,
            ).decode("utf-8")
        except UnicodeDecodeError:
            return f"Resource {resource.path} is not valid UTF-8 and cannot be loaded into the prompt."
        if len(content) > MAX_RUNTIME_RESOURCE_CHARS:
            content = content[:MAX_RUNTIME_RESOURCE_CHARS] + "\n[resource output truncated]"
        return content

    return [list_resources, read_resource]

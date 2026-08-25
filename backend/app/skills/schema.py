"""API contracts for standard Skill package lifecycle management."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.skills.package import MAX_SKILL_INSTRUCTIONS_BYTES

MAX_DRAFT_RESOURCE_FILES = 255
MAX_DRAFT_RESOURCE_BYTES = 8 * 1024 * 1024
MAX_DRAFT_RESOURCE_TOTAL_BYTES = 32 * 1024 * 1024
MAX_DRAFT_RESOURCE_BASE64_CHARS = 4 * ((MAX_DRAFT_RESOURCE_BYTES + 2) // 3)
MAX_DRAFT_RESOURCE_TOTAL_BASE64_CHARS = (
    4 * ((MAX_DRAFT_RESOURCE_TOTAL_BYTES + 2) // 3) + 4 * MAX_DRAFT_RESOURCE_FILES
)
MAX_SKILL_DRAFT_NON_RESOURCE_JSON_BYTES = 1024 * 1024
MAX_SKILL_DRAFT_JSON_BODY_BYTES = (
    MAX_DRAFT_RESOURCE_TOTAL_BASE64_CHARS + MAX_SKILL_DRAFT_NON_RESOURCE_JSON_BYTES
)
MAX_SKILL_JSON_BODY_BYTES = 1024 * 1024
MAX_SKILL_IMPORT_BODY_BYTES = 65 * 1024 * 1024
MAX_ROUTING_EXAMPLES_PER_GROUP = 64
MAX_ROUTING_EXAMPLE_CHARS = 512
MAX_ROUTING_EXAMPLES_TOTAL_CHARS = 8192


def validate_skill_instructions(value: str) -> str:
    if len(value.encode("utf-8")) > MAX_SKILL_INSTRUCTIONS_BYTES:
        raise ValueError("Skill instructions exceed the 64 KiB UTF-8 byte limit")
    return value


def validate_skill_resource_budget(resources: list[SkillResourceInput]) -> None:
    """Reject oversized editor payloads by encoded length before decoding any file."""

    if len(resources) > MAX_DRAFT_RESOURCE_FILES:
        raise ValueError(f"a Skill draft may contain at most {MAX_DRAFT_RESOURCE_FILES} resources")
    encoded_total = 0
    decoded_total = 0
    for resource in resources:
        encoded_length = len(resource.content_base64)
        encoded_total += encoded_length
        if encoded_total > MAX_DRAFT_RESOURCE_TOTAL_BASE64_CHARS:
            raise ValueError("Skill resource base64 payload exceeds the request encoding budget")

        padding = 2 if resource.content_base64.endswith("==") else int(resource.content_base64.endswith("="))
        decoded_upper_bound = 3 * ((encoded_length + 3) // 4) - padding
        if decoded_upper_bound > MAX_DRAFT_RESOURCE_BYTES:
            raise ValueError(f"resource {resource.path!r} exceeds the decoded 8 MiB file budget")
        decoded_total += max(decoded_upper_bound, 0)
        if decoded_total > MAX_DRAFT_RESOURCE_TOTAL_BYTES:
            raise ValueError("Skill resources exceed the decoded 32 MiB request budget")


def normalize_routing_examples(value: dict[str, list[str]]) -> dict[str, list[str]]:
    unexpected = set(value) - {"positive", "negative"}
    if unexpected:
        raise ValueError(f"unsupported routing example groups: {', '.join(sorted(unexpected))}")
    normalized: dict[str, list[str]] = {}
    total_chars = 0
    for key, items in value.items():
        if len(items) > MAX_ROUTING_EXAMPLES_PER_GROUP:
            raise ValueError(f"routing example group {key!r} exceeds {MAX_ROUTING_EXAMPLES_PER_GROUP} items")
        cleaned: list[str] = []
        for item in items:
            text = item.strip()
            if not text:
                continue
            if len(text) > MAX_ROUTING_EXAMPLE_CHARS:
                raise ValueError(f"routing example exceeds {MAX_ROUTING_EXAMPLE_CHARS} characters")
            total_chars += len(text)
            if total_chars > MAX_ROUTING_EXAMPLES_TOTAL_CHARS:
                raise ValueError("routing examples exceed the cumulative character budget")
            cleaned.append(text)
        normalized[key] = cleaned
    return normalized


class SkillResourceInput(BaseModel):
    path: str = Field(min_length=1, max_length=512)
    content_base64: str = Field(
        default="",
        max_length=MAX_DRAFT_RESOURCE_BASE64_CHARS,
        description="Base64 resource content; decoded content is limited to 8 MiB.",
        json_schema_extra={"x-max-decoded-bytes": MAX_DRAFT_RESOURCE_BYTES},
    )


class SkillResourceChanges(BaseModel):
    upsert: list[SkillResourceInput] = Field(
        default_factory=list,
        max_length=MAX_DRAFT_RESOURCE_FILES,
        description="Incremental resource additions and replacements within the request budgets.",
        json_schema_extra={
            "x-max-total-decoded-bytes": MAX_DRAFT_RESOURCE_TOTAL_BYTES,
            "x-max-total-base64-chars": MAX_DRAFT_RESOURCE_TOTAL_BASE64_CHARS,
        },
    )
    delete: list[str] = Field(default_factory=list, max_length=MAX_DRAFT_RESOURCE_FILES)

    @field_validator("delete")
    @classmethod
    def validate_deleted_paths(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(path.strip() for path in value if path.strip()))

    @model_validator(mode="after")
    def validate_upsert_budget(self):
        validate_skill_resource_budget(self.upsert)
        return self


class SkillDraftCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    description: str = Field(min_length=1, max_length=1024)
    instructions: str = ""
    frontmatter: dict[str, Any] = Field(default_factory=dict)
    resources: list[SkillResourceInput] = Field(
        default_factory=list,
        max_length=MAX_DRAFT_RESOURCE_FILES,
        description="Complete resource set within the request-level encoded and decoded budgets.",
        json_schema_extra={
            "x-max-total-decoded-bytes": MAX_DRAFT_RESOURCE_TOTAL_BYTES,
            "x-max-total-base64-chars": MAX_DRAFT_RESOURCE_TOTAL_BASE64_CHARS,
        },
    )
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    version_note: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def validate_resources_budget(self):
        validate_skill_resource_budget(self.resources)
        return self

    @field_validator("instructions")
    @classmethod
    def validate_instructions_budget(cls, value: str) -> str:
        return validate_skill_instructions(value)


class SkillDraftUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    description: str = Field(min_length=1, max_length=1024)
    instructions: str = ""
    frontmatter: dict[str, Any] = Field(default_factory=dict)
    resources: list[SkillResourceInput] | None = Field(
        default=None,
        max_length=MAX_DRAFT_RESOURCE_FILES,
        description="Optional complete replacement resource set within the request budgets.",
        json_schema_extra={
            "x-max-total-decoded-bytes": MAX_DRAFT_RESOURCE_TOTAL_BYTES,
            "x-max-total-base64-chars": MAX_DRAFT_RESOURCE_TOTAL_BASE64_CHARS,
        },
    )
    resource_changes: SkillResourceChanges | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    version_note: str = Field(default="", max_length=500)
    expected_revision: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_resource_update_mode(self):
        if self.resources is not None and self.resource_changes is not None:
            raise ValueError("resources and resource_changes cannot be submitted together")
        if self.resources is not None:
            validate_skill_resource_budget(self.resources)
        return self

    @field_validator("instructions")
    @classmethod
    def validate_instructions_budget(cls, value: str) -> str:
        return validate_skill_instructions(value)


class SkillPublishRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    enabled: bool = False
    default: bool = False
    visibility: Literal["public", "private"] = "public"
    order: int = Field(default=100, ge=0, le=100_000)
    tools: list[str] = Field(default_factory=list, max_length=256)
    always_on: bool = False
    routable: bool = True
    routing_examples: dict[str, list[str]] = Field(
        default_factory=dict,
        json_schema_extra={
            "x-max-items-per-group": MAX_ROUTING_EXAMPLES_PER_GROUP,
            "x-max-item-chars": MAX_ROUTING_EXAMPLE_CHARS,
            "x-max-total-chars": MAX_ROUTING_EXAMPLES_TOTAL_CHARS,
        },
    )

    @field_validator("routing_examples")
    @classmethod
    def validate_routing_examples(cls, value: dict[str, list[str]]) -> dict[str, list[str]]:
        return normalize_routing_examples(value)


class SkillSettingsUpdate(BaseModel):
    expected_revision: int = Field(ge=1)
    enabled: bool | None = None
    default: bool | None = None
    visibility: Literal["public", "private"] | None = None
    order: int | None = Field(default=None, ge=0, le=100_000)
    tools: list[str] | None = Field(default=None, max_length=256)
    always_on: bool | None = None
    routable: bool | None = None
    routing_examples: dict[str, list[str]] | None = Field(
        default=None,
        json_schema_extra={
            "x-max-items-per-group": MAX_ROUTING_EXAMPLES_PER_GROUP,
            "x-max-item-chars": MAX_ROUTING_EXAMPLE_CHARS,
            "x-max-total-chars": MAX_ROUTING_EXAMPLES_TOTAL_CHARS,
        },
    )

    @field_validator("routing_examples")
    @classmethod
    def validate_routing_examples(cls, value: dict[str, list[str]] | None) -> dict[str, list[str]] | None:
        return normalize_routing_examples(value) if value is not None else None


class SkillActivateRequest(BaseModel):
    expected_revision: int = Field(ge=1)


class SkillRollbackRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    version_id: str | None = Field(default=None, max_length=36)


class SkillArchiveRequest(BaseModel):
    expected_revision: int = Field(ge=1)


class SkillImportApproveRequest(SkillPublishRequest):
    expected_revision: int = Field(ge=0)
    expected_digest: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")


class SkillResourceResponse(BaseModel):
    path: str
    kind: str
    size: int
    sha256: str
    executable: bool = False


class SkillCompatibilityResponse(BaseModel):
    level: str
    format_compatible: bool
    runtime_ready: bool
    reasons: list[str] = Field(default_factory=list)


class SkillCatalogItem(BaseModel):
    id: str
    skill_id: str
    name: str
    label: str
    description: str
    tool_ids: list[str]
    is_default: bool
    enabled: bool
    visibility: str
    order: int
    always_on: bool
    routable: bool
    routing_examples: dict[str, list[str]]
    version: int
    revision: int
    digest: str
    status: str
    origin: dict[str, Any]
    compatibility: SkillCompatibilityResponse
    updated_at: str | None = None


class SkillCatalogResponse(BaseModel):
    revision: int
    skills: list[SkillCatalogItem]
    tools: list[dict[str, Any]]
    default_skill_ids: list[str]
    default_tool_ids: list[str]
    allowed_actions: list[str] = Field(default_factory=list)


class SkillDetailResponse(BaseModel):
    id: str
    skill_id: str
    name: str
    label: str
    description: str
    instructions: str
    frontmatter: dict[str, Any]
    resources: list[SkillResourceResponse]
    tools: list[str]
    default: bool
    enabled: bool
    visibility: str
    order: int
    always_on: bool
    routable: bool
    routing_examples: dict[str, list[str]]
    version: int
    version_id: str
    revision: int
    digest: str
    status: str
    origin: dict[str, Any]
    compatibility: SkillCompatibilityResponse
    capability_grants: dict[str, Any] = Field(default_factory=dict)
    allowed_actions: list[str]
    created_at: str | None = None
    updated_at: str | None = None


class SkillVersionResponse(BaseModel):
    id: str
    version: int
    digest: str
    status: str
    origin: dict[str, Any]
    version_note: str
    active: bool
    created_at: str | None = None


class SkillVersionsResponse(BaseModel):
    versions: list[SkillVersionResponse]


class SkillImportResponse(BaseModel):
    id: str
    status: str
    digest: str | None = None
    name: str | None = None
    revision: int | None = None
    compatibility: SkillCompatibilityResponse | None = None
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None

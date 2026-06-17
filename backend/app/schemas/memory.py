from datetime import datetime

from pydantic import BaseModel, Field


class MemoryCreate(BaseModel):
    type: str = Field(default="memo")
    title: str
    content: str | None = None
    priority: str = "medium"
    due_at: datetime | None = None
    remind_at: datetime | None = None
    source_type: str = "manual"
    source_id: str | None = None
    metadata_json: str | None = None


class MemoryUpdate(BaseModel):
    type: str | None = None
    title: str | None = None
    content: str | None = None
    status: str | None = None
    priority: str | None = None
    due_at: datetime | None = None
    remind_at: datetime | None = None
    metadata_json: str | None = None


class MemoryPostpone(BaseModel):
    days: int = 1

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """Canonical JSON response envelope for non-file, non-stream endpoints."""

    code: int | str = 200
    message: str = "success"
    data: T | None = None
    correlation_id: str | None = Field(default=None, exclude_if=lambda value: value is None)

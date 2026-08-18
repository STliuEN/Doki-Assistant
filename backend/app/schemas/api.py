from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """Canonical JSON response envelope for non-file, non-stream endpoints."""

    code: int = 200
    message: str = "success"
    data: T | None = None

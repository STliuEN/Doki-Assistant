from typing import TypeVar

from app.schemas.api import ApiResponse

T = TypeVar("T")


def success_response(
    message: str = "success",
    data: T | None = None,
    *,
    correlation_id: str | None = None,
) -> ApiResponse[T]:
    """Build the canonical response without bypassing FastAPI validation."""
    return ApiResponse(code=200, message=message, data=data, correlation_id=correlation_id)

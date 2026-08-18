import os
from functools import wraps

from django.core.cache import cache
from rest_framework import status
from rest_framework.response import Response


def _client_ip(request) -> str:
    if os.getenv("TRUST_PROXY_HEADERS", "false").lower() == "true":
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
        if forwarded:
            return forwarded
    return request.META.get("REMOTE_ADDR") or "unknown"


def rate_limit(*, scope: str, limit: int, window: int):
    """Apply an atomic fixed-window limit to a Django API view method."""

    def decorator(func):
        @wraps(func)
        def wrapper(self, request, *args, **kwargs):
            key = f"rate_limit:{scope}:{_client_ip(request)}"
            try:
                if cache.add(key, 1, timeout=window):
                    current = 1
                else:
                    current = cache.incr(key)
            except Exception:
                return Response(
                    {"detail": "Rate limit service unavailable"},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )

            if current > limit:
                return Response(
                    {"detail": "Too many requests"},
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )
            return func(self, request, *args, **kwargs)

        return wrapper

    return decorator

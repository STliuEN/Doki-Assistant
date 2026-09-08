"""Retire Django business routes; SQL writes belong to FastAPI after E4."""

from django.http import JsonResponse


class LegacyReadOnlyRouter:
    def db_for_write(self, model, **hints):
        raise RuntimeError("Legacy Django ORM writes are retired; use FastAPI")

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        return False


class LegacyBusinessReadOnlyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path.rstrip("/")
        legacy = path in {"/user", "/file", "/admin"} or path.startswith(("/user/", "/file/", "/admin/"))
        if legacy:
            return JsonResponse({"code": "E4_LEGACY_WRITE_RETIRED", "detail": "Use the FastAPI user and SQL business APIs"}, status=410)
        return self.get_response(request)

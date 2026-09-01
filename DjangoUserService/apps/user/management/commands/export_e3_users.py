from __future__ import annotations

import json
from datetime import UTC
from pathlib import Path
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from apps.user.models import GenderChoice, User, UserStatusChoice

_STATUS_NAMES = {
    UserStatusChoice.ACTIVE: "active",
    UserStatusChoice.DISABLED: "disabled",
    UserStatusChoice.LOCKED: "locked",
}
_GENDER_NAMES = {
    GenderChoice.MALE: "1",
    GenderChoice.FEMALE: "2",
    GenderChoice.OTHER: "3",
}


def _timestamp(value) -> str | None:
    if value is None:
        return None
    if timezone.is_naive(value):
        # This project currently stores naive values in TIME_ZONE because
        # USE_TZ is disabled; preserve their meaning before normalizing.
        value = timezone.make_aware(value, ZoneInfo(settings.TIME_ZONE))
    return value.astimezone(UTC).isoformat()


class Command(BaseCommand):
    help = "Export the Django user table through a read-only transaction for E3 migration"

    def add_arguments(self, parser) -> None:
        parser.add_argument("--output", required=True, help="Destination JSON path for the temporary source snapshot")

    def handle(self, *args, **options) -> None:
        if connection.vendor != "mysql":
            raise CommandError("E3 source export requires the configured Django MySQL database")

        # Make an accidental write from this command fail at the database layer.
        with connection.cursor() as cursor:
            cursor.execute("SET SESSION TRANSACTION READ ONLY")
            cursor.execute("SELECT @@session.transaction_read_only")
            if str(cursor.fetchone()[0]).upper() not in {"1", "ON"}:
                raise CommandError("Django source connection did not enter read-only mode")
            cursor.execute("SELECT DATABASE()")
            database_name = cursor.fetchone()[0]

        records: list[dict[str, object]] = []
        with transaction.atomic():
            users = User.objects.order_by("uuid").all()
            for user in users:
                status = _STATUS_NAMES.get(user.status)
                if status is None:
                    raise CommandError(f"Unsupported source user status for {user.uuid}")
                if status == "active" and not user.is_active:
                    raise CommandError(f"Source user {user.uuid} has an inconsistent active state")
                gender = None if user.gender is None else _GENDER_NAMES.get(user.gender)
                if user.gender is not None and gender is None:
                    raise CommandError(f"Unsupported source gender for {user.uuid}")
                records.append(
                    {
                        "id": str(user.uuid),
                        "username": user.username,
                        "email": user.email,
                        "telephone": user.telephone,
                        "password_hash": user.password,
                        "gender": gender,
                        "bio": user.bio,
                        "avatar": user.avatar,
                        "last_login": _timestamp(user.last_login),
                        "status": status,
                    }
                )

        output = Path(options["output"]).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "source_system": "django",
            "source_database": str(database_name or ""),
            "source_table": "user_service",
            "users": records,
        }
        output.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        self.stdout.write(f"E3 read-only source export completed: {len(records)} users -> {output}")

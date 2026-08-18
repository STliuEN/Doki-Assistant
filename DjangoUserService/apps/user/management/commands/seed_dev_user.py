import os

from django.core.management.base import BaseCommand, CommandError

from apps.user.models import User, UserStatusChoice


class Command(BaseCommand):
    help = "Explicitly create or update a development user; never runs at web startup."

    def add_arguments(self, parser):
        parser.add_argument("--username", default=os.getenv("DEV_USER_USERNAME", "dev"))
        parser.add_argument("--email", default=os.getenv("DEV_USER_EMAIL", "dev@example.invalid"))
        parser.add_argument("--password", required=True)

    def handle(self, *args, **options):
        if os.getenv("ENV", "dev").strip().lower() in {"prod", "production"}:
            raise CommandError("seed_dev_user is disabled in production")

        user, created = User.objects.get_or_create(
            email=options["email"],
            defaults={"username": options["username"]},
        )
        user.username = options["username"]
        user.status = UserStatusChoice.ACTIVE
        user.is_active = True
        user.set_password(options["password"])
        user.save()
        action = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{action} development user {user.username}"))

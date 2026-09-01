from datetime import UTC, datetime
from importlib import import_module
import json
import os
import subprocess
import sys
import time
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import jwt
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIClient

from .authentications import (
    JWT_ALGORITHM,
    JWT_AUDIENCE,
    JWT_ISSUER,
    JWTAuthentication,
    JWTTokenGenerator,
    TokenRevocationUnavailable,
    blacklist_key,
    decode_token,
)
from .models import User, UserStatusChoice


class E3ExportTimestampTests(SimpleTestCase):
    def test_naive_django_timestamp_is_normalized_from_project_timezone(self):
        command_module = import_module("apps.user.management.commands.export_e3_users")

        with override_settings(TIME_ZONE="Asia/Shanghai"):
            normalized = command_module._timestamp(datetime(2026, 9, 1, 12, 0, 0))

        self.assertEqual(normalized, "2026-09-01T04:00:00+00:00")
        self.assertEqual(command_module._timestamp(datetime(2026, 9, 1, 4, 0, 0, tzinfo=UTC)), "2026-09-01T04:00:00+00:00")

TEST_SECRET = "test-jwt-secret-with-at-least-32-characters"
AUTH_CONTRACT_PATH = Path(__file__).resolve().parents[3] / "contracts" / "auth_access_token.json"


class ProductionSettingsTests(SimpleTestCase):
    def _import_settings(self, **overrides):
        env = os.environ.copy()
        env.update(
            {
                "ENV": "production",
                "JWT_SECRET_KEY": "jwt-" + "a" * 40,
                "SECRET_KEY": "jwt-" + "a" * 40,
                "DJANGO_DEBUG": "false",
                "DJANGO_ALLOWED_HOSTS": "app.example.com",
                "CORS_ALLOW_ALL_ORIGINS": "false",
                "CORS_ALLOWED_ORIGINS": "https://app.example.com",
                "REDIS_CACHE_URL": "redis://redis:6379/1",
            }
        )
        env.update(overrides)
        return subprocess.run(
            [sys.executable, "-c", "from django.conf import settings; print(settings.SECRET_KEY)"],
            cwd=Path(__file__).resolve().parents[2],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_production_rejects_a_weak_jwt_secret(self):
        result = self._import_settings(JWT_SECRET_KEY="short", SECRET_KEY="short")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Production JWT secret", result.stderr)

        result = self._import_settings(ENV="staging")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unsupported ENV", result.stderr)

    def test_production_requires_explicit_cors_origins(self):
        result = self._import_settings(CORS_ALLOWED_ORIGINS="")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CORS_ALLOWED_ORIGINS", result.stderr)

    def test_production_requires_the_revocation_store(self):
        result = self._import_settings(REDIS_CACHE_URL="")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("REDIS_CACHE_URL", result.stderr)


class DeploymentReliabilityTests(TestCase):
    def test_seed_dev_user_is_explicit_and_idempotent(self):
        output = StringIO()
        command_args = {
            "username": "seed-user",
            "email": "seed@example.invalid",
            "password": "StrongPass123!",
            "stdout": output,
        }

        call_command("seed_dev_user", **command_args)
        call_command("seed_dev_user", **command_args)

        user = User.objects.get(email="seed@example.invalid")
        self.assertEqual(User.objects.filter(email=user.email).count(), 1)
        self.assertTrue(user.check_password("StrongPass123!"))
        self.assertIn("Updated development user", output.getvalue())

    @patch.dict(os.environ, {"ENV": "production"})
    def test_seed_dev_user_is_disabled_in_production(self):
        with self.assertRaisesRegex(CommandError, "disabled in production"):
            call_command(
                "seed_dev_user",
                username="seed-user",
                email="seed@example.invalid",
                password="StrongPass123!",
            )


def active_user():
    return SimpleNamespace(
        uuid="user-1",
        username="alice",
        email="alice@example.com",
        status=UserStatusChoice.ACTIVE,
    )


@override_settings(SECRET_KEY=TEST_SECRET)
class JWTTokenLifecycleTests(SimpleTestCase):
    def test_django_accepts_the_shared_cross_service_contract_fixture(self):
        contract = json.loads(AUTH_CONTRACT_PATH.read_text(encoding="utf-8"))

        payload = decode_token(contract["token"])

        self.assertEqual(
            {key: payload[key] for key in contract["claims"]},
            contract["claims"],
        )

    def test_pair_has_distinct_types_and_shared_session(self):
        pair = JWTTokenGenerator.generate_token_pair(active_user())

        access = decode_token(pair["token"])
        refresh = decode_token(pair["refresh_token"])

        self.assertEqual(access["token_type"], "access")
        self.assertEqual(refresh["token_type"], "refresh")
        self.assertEqual(access["sid"], refresh["sid"])
        self.assertNotEqual(access["jti"], refresh["jti"])

    def test_access_token_cannot_be_refreshed(self):
        access, _ = JWTTokenGenerator.generate_token(active_user())

        with self.assertRaisesRegex(AuthenticationFailed, "Refresh token required"):
            JWTTokenGenerator.refresh_token(access)

    def test_expired_refresh_token_is_rejected(self):
        now = int(time.time())
        token = jwt.encode(
            {
                "user_id": "user-1",
                "token_type": "refresh",
                "iss": JWT_ISSUER,
                "aud": JWT_AUDIENCE,
                "iat": now - 10,
                "nbf": now - 10,
                "exp": now - 1,
                "jti": "expired",
                "sid": "expired-session",
                "ver": 1,
            },
            TEST_SECRET,
            algorithm=JWT_ALGORITHM,
        )

        with self.assertRaisesRegex(AuthenticationFailed, "expired"):
            JWTTokenGenerator.refresh_token(token)

    @patch("apps.user.authentications.cache.add", return_value=True)
    @patch("apps.user.authentications.cache.get", return_value=None)
    @patch("apps.user.authentications.User.objects.get", return_value=active_user())
    def test_refresh_rotates_once(self, _get_user, _cache_get, cache_add):
        refresh, _ = JWTTokenGenerator.generate_token(active_user(), token_type="refresh")

        pair = JWTTokenGenerator.refresh_token(refresh)

        self.assertEqual(decode_token(pair["token"])["token_type"], "access")
        self.assertEqual(decode_token(pair["refresh_token"])["token_type"], "refresh")
        old_jti = decode_token(refresh)["jti"]
        self.assertEqual(cache_add.call_args.args[0], blacklist_key(old_jti))

    @patch("apps.user.authentications.cache.get", return_value="1")
    def test_revoked_refresh_token_is_rejected(self, _cache_get):
        refresh, _ = JWTTokenGenerator.generate_token(active_user(), token_type="refresh")

        with self.assertRaisesRegex(AuthenticationFailed, "revoked"):
            JWTTokenGenerator.refresh_token(refresh)

    def test_refresh_token_cannot_authenticate_business_request(self):
        refresh, _ = JWTTokenGenerator.generate_token(active_user(), token_type="refresh")
        request = SimpleNamespace(headers={"Authorization": f"Bearer {refresh}"})

        with self.assertRaisesRegex(AuthenticationFailed, "Access token required"):
            JWTAuthentication().authenticate(request)

    def test_access_token_without_required_lifecycle_claims_is_rejected(self):
        now = int(time.time())
        payload = {
            "user_id": "user-1",
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
            "iat": now,
            "nbf": now,
            "exp": now + 300,
            "jti": "legacy-token",
            "sid": "legacy-session",
            "ver": 1,
        }
        token = jwt.encode(payload, TEST_SECRET, algorithm=JWT_ALGORITHM)
        request = SimpleNamespace(headers={"Authorization": f"Bearer {token}"})

        with self.assertRaisesRegex(AuthenticationFailed, "Invalid token"):
            JWTAuthentication().authenticate(request)

        for missing_claim in ("sid", "ver", "exp", "iat", "nbf"):
            incomplete_payload = {**payload, "token_type": "access"}
            incomplete_payload.pop(missing_claim)
            incomplete_token = jwt.encode(incomplete_payload, TEST_SECRET, algorithm=JWT_ALGORITHM)
            with self.assertRaises(jwt.InvalidTokenError):
                decode_token(incomplete_token)

    @patch("apps.user.authentications.cache.set", side_effect=RuntimeError("redis unavailable"))
    def test_blacklist_write_outage_is_not_reported_as_success(self, _cache_set):
        access, _ = JWTTokenGenerator.generate_token(active_user())

        with self.assertLogs("apps.user.authentications", level="ERROR"):
            with self.assertRaises(TokenRevocationUnavailable):
                JWTTokenGenerator.blacklist_token(access)


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
)
class UserApiFlowTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.registration = {
            "username": "flow-user",
            "email": "flow@example.com",
            "password": "StrongPass123!",
            "confirm_password": "StrongPass123!",
        }

    def test_register_refresh_replay_logout_flow(self):
        registered = self.client.post("/user/register/", self.registration, format="json")
        self.assertEqual(registered.status_code, 201)
        access = registered.data["token"]
        refresh = registered.data["refresh_token"]
        self.assertEqual(decode_token(access)["token_type"], "access")
        self.assertEqual(decode_token(refresh)["token_type"], "refresh")

        refreshed = self.client.post(
            "/user/refresh-token/",
            {"refresh_token": refresh},
            format="json",
        )
        self.assertEqual(refreshed.status_code, 200)

        replay = self.client.post(
            "/user/refresh-token/",
            {"refresh_token": refresh},
            format="json",
        )
        self.assertEqual(replay.status_code, 401)

        new_access = refreshed.data["token"]
        new_refresh = refreshed.data["refresh_token"]
        logged_out = self.client.post(
            "/user/logout/",
            {"refresh_token": new_refresh},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {new_access}",
        )
        self.assertEqual(logged_out.status_code, 200)

        rejected = self.client.get(
            "/user/detail/",
            HTTP_AUTHORIZATION=f"Bearer {new_access}",
        )
        self.assertEqual(rejected.status_code, 401)

    def test_password_reset_invalidates_the_previous_token_version(self):
        registered = self.client.post("/user/register/", self.registration, format="json")
        self.assertEqual(registered.status_code, 201)
        old_access = registered.data["token"]

        reset = self.client.post(
            "/user/reset-password/",
            {
                "old_password": self.registration["password"],
                "new_password": "NewStrongPass456!",
                "confirm_password": "NewStrongPass456!",
            },
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {old_access}",
        )
        self.assertEqual(reset.status_code, 200)

        rejected = self.client.get(
            "/user/detail/",
            HTTP_AUTHORIZATION=f"Bearer {old_access}",
        )
        self.assertEqual(rejected.status_code, 401)

        accepted = self.client.get(
            "/user/detail/",
            HTTP_AUTHORIZATION=f"Bearer {reset.data['token']}",
        )
        self.assertEqual(accepted.status_code, 200)

    def test_inactive_user_cannot_login(self):
        registered = self.client.post("/user/register/", self.registration, format="json")
        self.assertEqual(registered.status_code, 201)
        user = User.objects.get(email=self.registration["email"])
        user.is_active = False
        user.save(update_fields=["is_active"])

        response = self.client.post(
            "/user/login/",
            {"username": user.username, "password": self.registration["password"]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_refresh_returns_503_when_revocation_store_is_unavailable(self):
        registered = self.client.post("/user/register/", self.registration, format="json")
        self.assertEqual(registered.status_code, 201)

        def fail_blacklist_write(key, *_args, **_kwargs):
            if str(key).startswith("blacklist:"):
                raise RuntimeError("redis unavailable")
            return True

        with (
            patch(
                "apps.user.authentications.cache.add",
                side_effect=fail_blacklist_write,
            ),
            self.assertLogs("apps.user.authentications", level="ERROR"),
        ):
            response = self.client.post(
                "/user/refresh-token/",
                {"refresh_token": registered.data["refresh_token"]},
                format="json",
            )

        self.assertEqual(response.status_code, 503)

    def test_logout_returns_503_when_revocation_store_is_unavailable(self):
        registered = self.client.post("/user/register/", self.registration, format="json")
        self.assertEqual(registered.status_code, 201)

        with (
            patch(
                "apps.user.authentications.cache.set",
                side_effect=RuntimeError("redis unavailable"),
            ),
            self.assertLogs("apps.user.authentications", level="ERROR"),
        ):
            response = self.client.post(
                "/user/logout/",
                {"refresh_token": registered.data["refresh_token"]},
                format="json",
                HTTP_AUTHORIZATION=f"Bearer {registered.data['token']}",
            )

        self.assertEqual(response.status_code, 503)

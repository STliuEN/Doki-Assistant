"""Pytest bootstrap with fail-closed isolation from local runtime data."""

import logging
import os
import sys
import tempfile
from pathlib import Path

BACKEND_ROOT = Path(__file__).parent
REPO_ROOT = BACKEND_ROOT.parent

sys.path.insert(0, str(BACKEND_ROOT))
sys.path.insert(0, str(REPO_ROOT))

_TEST_RESOURCE_DIRECTORY = tempfile.TemporaryDirectory(
    prefix="doki-pytest-",
    ignore_cleanup_errors=True,
)
TEST_RESOURCE_ROOT = Path(_TEST_RESOURCE_DIRECTORY.name).resolve()

# These values must exist before application modules call load_dotenv(). Tests
# therefore cannot inherit live localhost services or persistent application data.
_ISOLATED_ENVIRONMENT = {
    "ENV": "test",
    "MYSQL_HOST": "127.0.0.1",
    "MYSQL_PORT": "1",
    "MYSQL_USER": "pytest",
    "MYSQL_PASSWORD": "pytest",
    "MYSQL_DATABASE": "doki_pytest",
    "REDIS_HOST": "127.0.0.1",
    "REDIS_PORT": "1",
    "REDIS_DB": "15",
    "DJANGO_API_URL": "http://127.0.0.1:1",
    "AUTH_JWT_SECRET": "pytest-e3-auth-secret-with-at-least-32-characters",
    "SKILL_STORAGE_BACKEND": "filesystem",
    "SKILL_STORAGE_DIR": str(TEST_RESOURCE_ROOT / "skill_packages"),
    "SKILL_STORAGE_SHARED": "false",
    "SKILL_MULTI_INSTANCE": "false",
    "LANGCHAIN_TRACING_V2": "false",
    "RATE_LIMIT_ENABLED": "false",
}
os.environ.update(_ISOLATED_ENVIRONMENT)

# Chroma and its sidecar paths are YAML-backed rather than environment-backed.
# Mutate their shared config mapping before test modules import any RAG service.
from app.utils.config import chroma_config  # noqa: E402

chroma_config.update(
    {
        "persist_directory": str(TEST_RESOURCE_ROOT / "chromadb"),
        "data_path": str(TEST_RESOURCE_ROOT / "knowledge"),
        "md5_hex_store": str(TEST_RESOURCE_ROOT / "md5_hex_store" / "md5_hex_store.txt"),
    }
)

from app.core.logger_handler import DEFAULT_LOGGING_FORMAT, logger  # noqa: E402

for _handler in tuple(logger.handlers):
    if isinstance(_handler, logging.FileHandler):
        logger.removeHandler(_handler)
        _handler.close()

_TEST_LOG_DIRECTORY = TEST_RESOURCE_ROOT / "logs"
_TEST_LOG_DIRECTORY.mkdir(parents=True, exist_ok=True)
_TEST_LOG_HANDLER = logging.FileHandler(
    _TEST_LOG_DIRECTORY / "agent-pytest.log",
    encoding="utf-8",
)
_TEST_LOG_HANDLER.setLevel(logging.DEBUG)
_TEST_LOG_HANDLER.setFormatter(DEFAULT_LOGGING_FORMAT)
logger.addHandler(_TEST_LOG_HANDLER)


def pytest_sessionfinish(session, exitstatus) -> None:
    del session, exitstatus
    logger.removeHandler(_TEST_LOG_HANDLER)
    _TEST_LOG_HANDLER.close()
    _TEST_RESOURCE_DIRECTORY.cleanup()

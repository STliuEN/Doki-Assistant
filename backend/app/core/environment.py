import os

from dotenv import load_dotenv

SUPPORTED_ENVIRONMENTS = frozenset({"dev", "development", "test", "testing", "prod", "production"})
PRODUCTION_ENVIRONMENTS = frozenset({"prod", "production"})


def normalize_environment(value: str | None = None) -> str:
    """Return a supported runtime environment or fail before startup."""
    load_dotenv()
    environment = (value if value is not None else os.getenv("ENV", "dev")).strip().lower()
    if environment not in SUPPORTED_ENVIRONMENTS:
        supported = ", ".join(sorted(SUPPORTED_ENVIRONMENTS))
        raise RuntimeError(f"Unsupported ENV {environment!r}; expected one of: {supported}")
    return environment


def is_production_environment(environment: str) -> bool:
    return environment in PRODUCTION_ENVIRONMENTS

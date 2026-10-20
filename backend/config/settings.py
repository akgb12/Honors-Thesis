import os
import secrets
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
REPOSITORY_ROOT = BASE_DIR.parent
load_dotenv(REPOSITORY_ROOT / ".env")


def _env_bool(name: str, default: bool) -> bool:
    # Parse a boolean environment setting
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name: str) -> list[str]:
    # Parse a comma separated environment setting
    values: list[str] = []
    for value in os.getenv(name, "").split(","):
        item = value.strip()
        if item:
            values.append(item)
    return values


def _repository_path(name: str, default: str) -> Path:
    # Resolve a path setting against the repository root
    value = Path(os.getenv(name) or default)
    if not value.is_absolute():
        value = REPOSITORY_ROOT / value
    return value.resolve()


def _secret_key(debug: bool) -> str:
    # Use the configured key or persist a random development key
    configured = os.getenv("DJANGO_SECRET_KEY")
    if configured:
        return configured
    if not debug:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY is required when DJANGO_DEBUG is false")
    key_file = REPOSITORY_ROOT / ".cache" / "dev_secret_key"
    if key_file.is_file():
        return key_file.read_text(encoding="utf-8").strip()
    key_file.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_urlsafe(50)
    key_file.write_text(key, encoding="utf-8")
    key_file.chmod(0o600)
    return key


DEBUG = _env_bool("DJANGO_DEBUG", True)
SECRET_KEY = _secret_key(DEBUG)
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "corsheaders",
    "django_tasks_db",
    "projects",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "ninja.compatibility.files.fix_request_files_middleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES: list[dict[str, object]] = []
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": dj_database_url.config(
        default="postgres://localhost:5432/honors_thesis",
        conn_max_age=60,
    )
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"
LANGUAGE_CODE = "en-us"
STATIC_URL = "static/"

STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": os.getenv("AWS_STORAGE_BUCKET_NAME", "honors-thesis"),
            "endpoint_url": os.getenv("AWS_S3_ENDPOINT_URL") or None,
            "access_key": os.getenv("AWS_ACCESS_KEY_ID") or None,
            "secret_key": os.getenv("AWS_SECRET_ACCESS_KEY") or None,
            "region_name": os.getenv("AWS_S3_REGION_NAME") or "us-east-1",
            "addressing_style": os.getenv("AWS_S3_ADDRESSING_STYLE") or "path",
            "signature_version": "s3v4",
            "file_overwrite": True,
            "querystring_auth": False,
        },
    },
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

SCRATCH_DIR = _repository_path("SCRATCH_DIR", ".cache/scratch")

CORS_ALLOWED_ORIGINS = _env_list("CORS_ALLOWED_ORIGINS")

TASKS = {
    "default": {
        "BACKEND": os.getenv(
            "DJANGO_TASK_BACKEND",
            "django_tasks_db.DatabaseBackend",
        ),
    }
}

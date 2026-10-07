import os
from pathlib import Path

import dj_database_url
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


SECRET_KEY = os.getenv("DJANGO_SECRET_KEY") or "local-development-only"
DEBUG = _env_bool("DJANGO_DEBUG", True)
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

media_setting = Path(os.getenv("MEDIA_ROOT", "storage"))
if not media_setting.is_absolute():
    media_setting = REPOSITORY_ROOT / media_setting
MEDIA_ROOT = media_setting.resolve()
MEDIA_URL = "/media/"

CORS_ALLOWED_ORIGINS = _env_list("CORS_ALLOWED_ORIGINS")

TASKS = {
    "default": {
        "BACKEND": os.getenv(
            "DJANGO_TASK_BACKEND",
            "django_tasks_db.DatabaseBackend",
        ),
    }
}

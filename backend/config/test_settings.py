import dj_database_url

from config.settings import *

DATABASES = {
    "default": dj_database_url.parse("postgresql:///honors_thesis"),
}

TASKS = {
    "default": {
        "BACKEND": "django.tasks.backends.immediate.ImmediateBackend",
    }
}

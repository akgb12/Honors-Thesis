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

# Tests talk to the moto S3 mock: no custom endpoint, so code that only works on SeaweedFS fails
TEST_BUCKET_NAME = "test-bucket"
STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": TEST_BUCKET_NAME,
            "endpoint_url": None,
            "access_key": "testing",
            "secret_key": "testing",
            "region_name": "us-east-1",
            "addressing_style": "virtual",
            "signature_version": "s3v4",
            "file_overwrite": True,
            "querystring_auth": False,
        },
    },
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

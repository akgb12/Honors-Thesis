import io
import json
import zipfile
from pathlib import Path

import boto3
import pytest
from django.conf import settings as django_settings
from django.core.files.storage import default_storage, storages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client
from django.test.client import BOUNDARY, MULTIPART_CONTENT, encode_multipart
from django.utils.functional import empty
from moto import mock_aws

from projects.models import Project, Run
from projects.storage import UnsafePathError, validate_relative_path

REPOSITORY_ROOT = Path(__file__).parents[3]
LECTURE_SAMPLE = REPOSITORY_ROOT / "pipeline" / "tests" / "fixtures" / "lecture_sample"


@pytest.fixture(autouse=True)
def s3_storage(settings, tmp_path: Path):
    # Back every backend test with a fresh moto S3 bucket and scratch folder
    settings.SCRATCH_DIR = tmp_path / "scratch"
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(
            Bucket=django_settings.TEST_BUCKET_NAME
        )
        storages._storages = {}
        default_storage._wrapped = empty
        yield
    storages._storages = {}
    default_storage._wrapped = empty


@pytest.fixture
def client() -> Client:
    # Create a Django API test client
    return Client()


def _create_project(client: Client, name: str = "Lecture") -> dict[str, object]:
    # Create one project through the API
    response = client.post(
        "/api/projects",
        data=json.dumps({"name": name}),
        content_type="application/json",
    )
    assert response.status_code == 201
    return response.json()


def _lecture_zip() -> bytes:
    # Build a complete lecture fixture archive in memory
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source in sorted(LECTURE_SAMPLE.rglob("*")):
            if source.is_file():
                archive.write(source, source.relative_to(LECTURE_SAMPLE).as_posix())
    return stream.getvalue()


@pytest.mark.django_db
def test_project_crud(client: Client) -> None:
    # Exercise project creation listing detail update and deletion
    created = _create_project(client)
    project_id = created["id"]

    listed = client.get("/api/projects")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == project_id

    detail = client.get(f"/api/projects/{project_id}")
    assert detail.status_code == 200
    assert detail.json()["name"] == "Lecture"

    updated = client.patch(
        f"/api/projects/{project_id}",
        data=json.dumps({"name": "Updated lecture"}),
        content_type="application/json",
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Updated lecture"

    deleted = client.delete(f"/api/projects/{project_id}")
    assert deleted.status_code == 204
    assert not Project.objects.filter(id=project_id).exists()


@pytest.mark.django_db
def test_multi_file_upload_replaces_existing_path(client: Client) -> None:
    # Upload multiple files and replace one matching path
    project = _create_project(client)
    project_id = project["id"]
    response = client.post(
        f"/api/projects/{project_id}/upload",
        {
            "files": [
                SimpleUploadedFile("main.tex", b"first"),
                SimpleUploadedFile("notes.txt", b"notes"),
            ]
        },
    )
    assert response.status_code == 200
    paths: list[str] = []
    for record in response.json()["files"]:
        paths.append(record["path"])
    assert paths == ["main.tex", "notes.txt"]

    replaced = client.post(
        f"/api/projects/{project_id}/upload",
        {"files": [SimpleUploadedFile("main.tex", b"second")]},
    )
    assert replaced.status_code == 200
    record = Project.objects.get(id=project_id).files.get(path="main.tex")
    assert record.size == 6


@pytest.mark.django_db
def test_zip_upload_uses_safe_extraction(client: Client) -> None:
    # Reject traversal in an uploaded zip archive
    project = _create_project(client)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("../outside.tex", "unsafe")
    upload = SimpleUploadedFile("project.zip", stream.getvalue())
    response = client.post(
        f"/api/projects/{project['id']}/upload",
        {"files": [upload]},
    )
    assert response.status_code == 400
    assert Project.objects.get(id=project["id"]).files.count() == 0


def test_uploaded_paths_reject_absolute_and_traversal() -> None:
    # Reject unsafe project and artifact style paths
    unsafe = [
        "/tmp/main.tex",
        "../main.tex",
        "figs/../../main.tex",
        r"C:\main.tex",
        "figs//a.png",
        "figs/",
        "",
    ]
    for value in unsafe:
        with pytest.raises(UnsafePathError):
            validate_relative_path(value)


@pytest.mark.django_db
def test_missing_file_put_flow(client: Client) -> None:
    # Fill a missing image slot and clear preflight findings
    project = _create_project(client)
    project_id = project["id"]
    main_source = (LECTURE_SAMPLE / "main.tex").read_bytes()
    uploaded = client.post(
        f"/api/projects/{project_id}/upload",
        {"files": [SimpleUploadedFile("main.tex", main_source)]},
    )
    assert uploaded.status_code == 200

    missing = client.get(f"/api/projects/{project_id}/preflight")
    assert missing.status_code == 200
    assert missing.json()["missing_images"] == ["figs/regression"]
    assert not missing.json()["ok"]

    image = (LECTURE_SAMPLE / "figs" / "regression.png").read_bytes()
    put_data = encode_multipart(
        BOUNDARY,
        {"file": SimpleUploadedFile("regression.png", image, content_type="image/png")},
    )
    filled = client.put(
        f"/api/projects/{project_id}/files/figs/regression",
        data=put_data,
        content_type=MULTIPART_CONTENT,
    )
    assert filled.status_code == 200
    assert Project.objects.get(id=project_id).files.filter(path="figs/regression.png").exists()

    ready = client.get(f"/api/projects/{project_id}/preflight")
    assert ready.status_code == 200
    assert ready.json()["ok"]
    assert ready.json()["missing_images"] == []
    assert ready.json()["critical_blockers"] == []


@pytest.mark.django_db(transaction=True)
@pytest.mark.tex
@pytest.mark.slow
def test_medium_run_review_and_artifact_downloads(client: Client) -> None:
    # Run the complete fake pipeline and inspect review artifacts
    project = _create_project(client)
    project_id = project["id"]
    upload = SimpleUploadedFile(
        "lecture_sample.zip",
        _lecture_zip(),
        content_type="application/zip",
    )
    uploaded = client.post(
        f"/api/projects/{project_id}/upload",
        {"files": [upload]},
    )
    assert uploaded.status_code == 200

    preflight = client.get(f"/api/projects/{project_id}/preflight")
    assert preflight.status_code == 200
    assert preflight.json()["ok"]
    assert preflight.json()["main_file"] == "main.tex"

    queued = client.post(
        f"/api/projects/{project_id}/runs",
        data=json.dumps(
            {
                "effort": "medium",
                "seed_weak": "slide_04/figure_01",
            }
        ),
        content_type="application/json",
    )
    assert queued.status_code == 202
    run_id = queued.json()["id"]
    run = Run.objects.get(id=run_id)
    assert run.status == Run.Status.SUCCEEDED
    assert run.storage_prefix == f"runs/{run.id}"
    assert run.model_provider == "fake"
    assert run.input_tokens == 24
    assert run.output_tokens == 16

    review = client.get(f"/api/runs/{run_id}/review")
    assert review.status_code == 200
    review_data = review.json()
    figure = None
    for element in review_data["elements"]:
        if element["id"] == "slide_04/figure_01":
            figure = element
            break
    assert figure is not None
    assert figure["status"] == "model_generated"
    assert figure["alt"]
    assert review_data["pages"]
    assert review_data["round_history"]

    artifacts = [
        "output/tagged.pdf",
        "output/updated_project.zip",
        "report.html",
        review_data["pages"][0]["image_url"].split("/artifact/", 1)[1],
    ]
    for artifact in artifacts:
        response = client.get(f"/api/runs/{run_id}/artifact/{artifact}")
        assert response.status_code == 200

    traversal = client.get(f"/api/runs/{run_id}/artifact/%2E%2E/manifest.json")
    assert traversal.status_code in {400, 404}

    keys = _stored_keys()
    assert f"runs/{run_id}/output/tagged.pdf" in keys
    assert f"runs/{run_id}/manifest.json" in keys
    assert f"runs/{run_id}/ir_final.json" in keys
    assert not any(key.startswith(f"runs/{run_id}/work/original/") for key in keys)
    assert not any(key.startswith(f"runs/{run_id}/work/marked/") for key in keys)
    assert not list((Path(django_settings.SCRATCH_DIR)).glob("*"))
    page = review_data["pages"][0]
    assert page["width_points"] > 0
    assert page["height_points"] > 0

    deleted = client.delete(f"/api/projects/{project_id}")
    assert deleted.status_code == 204
    assert _stored_keys() == []


def _stored_keys() -> list[str]:
    # List every object key in the test bucket
    client = boto3.client("s3", region_name="us-east-1")
    keys: list[str] = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=django_settings.TEST_BUCKET_NAME):
        for item in page.get("Contents", []):
            keys.append(item["Key"])
    return sorted(keys)


@pytest.mark.django_db
def test_project_files_are_stored_under_plain_keys(client: Client) -> None:
    # Store project files at projects/<id>/files/<path> in the bucket
    project = _create_project(client)
    client.post(
        f"/api/projects/{project['id']}/upload",
        {"files": [SimpleUploadedFile("main.tex", b"x")]},
    )
    assert _stored_keys() == [f"projects/{project['id']}/files/main.tex"]


@pytest.mark.django_db
def test_artifact_rejects_traversal_and_unlisted_paths(client: Client) -> None:
    # Only approved relative artifact paths are served
    project = Project.objects.create(name="p")
    run = Run.objects.create(
        project=project,
        effort="low",
        model_provider="fake",
        storage_prefix="runs/abc",
    )
    for path in ["manifest.json", "output/../manifest.json", "work/original/main.pdf"]:
        response = client.get(f"/api/runs/{run.id}/artifact/{path}")
        assert response.status_code in {400, 404}
    missing = client.get(f"/api/runs/{run.id}/artifact/report.html")
    assert missing.status_code == 404


def test_ensure_bucket_is_idempotent(settings) -> None:
    # Create a missing bucket once and leave an existing one alone
    options = {**settings.STORAGES["default"]["OPTIONS"], "bucket_name": "another-bucket"}
    settings.STORAGES = {
        **settings.STORAGES,
        "default": {**settings.STORAGES["default"], "OPTIONS": options},
    }
    first = io.StringIO()
    call_command("ensure_bucket", stdout=first)
    second = io.StringIO()
    call_command("ensure_bucket", stdout=second)
    assert "Created bucket another-bucket" in first.getvalue()
    assert "already exists" in second.getvalue()


def test_backend_code_follows_storage_rules() -> None:
    # Backend code never opens stored files by path or uses presigned URLs
    forbidden = [
        "generate_presigned",
        "presigned",
        "FileSystemStorage",
        "MEDIA_ROOT",
        "default_storage.path(",
        'querystring_auth": True',
        "put_object_acl",
        "default_acl",
    ]
    backend_root = Path(__file__).parents[2]
    for source in list((backend_root / "projects").rglob("*.py")) + [
        backend_root / "config" / "settings.py"
    ]:
        if source.name == "test_api.py":
            continue
        text = source.read_text(encoding="utf-8")
        for word in forbidden:
            assert word not in text, f"{word} found in {source.name}"

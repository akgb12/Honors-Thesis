import hashlib
import json
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, BinaryIO
from uuid import uuid4

from django.conf import settings
from django.core.files import File
from django.core.files.storage import default_storage
from django.db import transaction

from a11y_pipeline.bundle.unzip import safe_extract_zip
from projects.models import Project, ProjectFile


class UnsafePathError(ValueError):
    pass


def validate_relative_path(value: str) -> str:
    # Validate one relative POSIX storage path
    if not value or "\x00" in value or "\\" in value:
        raise UnsafePathError("Path must be a nonempty relative POSIX path")
    if value.startswith("/") or value.endswith("/") or "//" in value:
        raise UnsafePathError("Path must not contain empty segments")
    posix_path = PurePosixPath(value)
    windows_path = PureWindowsPath(value)
    if posix_path.is_absolute() or windows_path.is_absolute() or windows_path.drive:
        raise UnsafePathError("Absolute paths are not allowed")
    if ".." in posix_path.parts or "." in posix_path.parts:
        raise UnsafePathError("Path traversal is not allowed")
    normalized = posix_path.as_posix()
    if normalized in {"", "."}:
        raise UnsafePathError("Path must name a file")
    return normalized


def project_storage_path(project_id: object, relative_path: str) -> str:
    # Build a validated project storage name
    safe_path = validate_relative_path(relative_path)
    return f"projects/{project_id}/files/{safe_path}"


def run_storage_key(run_id: object, relative_path: str) -> str:
    # Build a validated run output storage name
    safe_path = validate_relative_path(relative_path)
    return f"runs/{run_id}/{safe_path}"


@contextmanager
def scratch_dir(name: str) -> Iterator[Path]:
    # Provide a local working folder that is always removed afterwards
    root = Path(settings.SCRATCH_DIR) / f"{name}-{uuid4().hex[:8]}"
    root.mkdir(parents=True, exist_ok=False)
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def save_project_file(
    project: Project,
    relative_path: str,
    content: BinaryIO,
) -> ProjectFile:
    # Replace one project file through Django storage
    safe_path = validate_relative_path(relative_path)
    storage_path = project_storage_path(project.id, safe_path)
    if default_storage.exists(storage_path):
        default_storage.delete(storage_path)
    saved_path = default_storage.save(storage_path, File(content))
    if saved_path != storage_path:
        default_storage.delete(saved_path)
        raise RuntimeError("Storage changed the requested project path")
    digest = hashlib.sha256()
    size = 0
    with default_storage.open(storage_path, "rb") as stored:
        while True:
            block = stored.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
            size += len(block)
    with transaction.atomic():
        record, _ = ProjectFile.objects.update_or_create(
            project=project,
            path=safe_path,
            defaults={"size": size, "sha256": digest.hexdigest()},
        )
    return record


def upload_project_files(project: Project, uploads: list[object]) -> list[ProjectFile]:
    # Save a zip bundle or multiple individual uploads
    if not uploads:
        raise ValueError("At least one file is required")
    if len(uploads) == 1 and str(uploads[0].name).lower().endswith(".zip"):
        return _upload_zip(project, uploads[0])
    saved: list[ProjectFile] = []
    for upload in uploads:
        if str(upload.name).lower().endswith(".zip"):
            raise ValueError("A zip archive must be uploaded by itself")
        saved.append(save_project_file(project, str(upload.name), upload))
    return saved


def save_missing_slot(project: Project, slot: str, upload: object) -> ProjectFile:
    # Fill a missing path while preserving the uploaded extension
    safe_slot = validate_relative_path(slot)
    upload_name = validate_relative_path(str(upload.name))
    destination = safe_slot
    if not PurePosixPath(safe_slot).suffix:
        suffix = PurePosixPath(upload_name).suffix
        if suffix:
            destination = f"{safe_slot}{suffix}"
    return save_project_file(project, destination, upload)


def materialize_project(project: Project, destination: Path) -> None:
    # Copy all project files from storage into a bundle folder
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    for project_file in project.files.all():
        relative = validate_relative_path(project_file.path)
        output = (root / relative).resolve()
        if not output.is_relative_to(root):
            raise UnsafePathError("Stored project path escapes the bundle")
        output.parent.mkdir(parents=True, exist_ok=True)
        storage_path = project_storage_path(project.id, relative)
        with default_storage.open(storage_path, "rb") as source, output.open("wb") as target:
            shutil.copyfileobj(source, target)


def delete_project_files(project: Project) -> None:
    # Delete all project inputs through Django storage
    for project_file in project.files.all():
        storage_path = project_storage_path(project.id, project_file.path)
        if default_storage.exists(storage_path):
            default_storage.delete(storage_path)


def delete_project_file(project: Project, relative_path: str) -> bool:
    # Delete one project input from storage and the database
    safe_path = validate_relative_path(relative_path)
    storage_path = project_storage_path(project.id, safe_path)
    if default_storage.exists(storage_path):
        default_storage.delete(storage_path)
    deleted, _ = ProjectFile.objects.filter(project=project, path=safe_path).delete()
    return deleted > 0


def upload_run_folder(run_id: object, folder: Path, skip: tuple[str, ...] = ()) -> int:
    # Upload one finished run folder to runs/<run_id>/ and return the file count
    root = folder.resolve()
    uploaded = 0
    for source in sorted(root.rglob("*")):
        if not source.is_file():
            continue
        relative = source.relative_to(root).as_posix()
        if any(relative == name or relative.startswith(f"{name}/") for name in skip):
            continue
        key = run_storage_key(run_id, relative)
        if default_storage.exists(key):
            default_storage.delete(key)
        with source.open("rb") as stream:
            saved = default_storage.save(key, File(stream))
        if saved != key:
            default_storage.delete(saved)
            raise RuntimeError("Storage changed the requested run path")
        uploaded += 1
    return uploaded


def run_file_exists(prefix: str, relative_path: str) -> bool:
    # Check for one stored run file by its relative path
    return default_storage.exists(f"{prefix}/{validate_relative_path(relative_path)}")


def read_run_json(prefix: str, relative_path: str) -> Any:
    # Read and decode one JSON file stored with a run
    key = f"{prefix}/{validate_relative_path(relative_path)}"
    with default_storage.open(key, "rb") as stored:
        return json.loads(stored.read().decode("utf-8"))


def list_run_files(prefix: str, folder: str) -> list[str]:
    # List file names directly inside one stored run folder
    _, names = default_storage.listdir(f"{prefix}/{validate_relative_path(folder)}")
    return sorted(names)


def delete_prefix(prefix: str) -> None:
    # Delete every stored object below a prefix
    directories, names = default_storage.listdir(prefix)
    for name in names:
        default_storage.delete(f"{prefix}/{name}")
    for directory in directories:
        delete_prefix(f"{prefix}/{directory}")


def _upload_zip(project: Project, upload: object) -> list[ProjectFile]:
    # Extract one archive with the pipeline safety checks
    with scratch_dir("upload") as root:
        archive_path = root / "upload.zip"
        with archive_path.open("wb") as archive:
            for chunk in upload.chunks():
                archive.write(chunk)
        extracted_root = root / "extracted"
        paths = safe_extract_zip(archive_path, extracted_root)
        saved: list[ProjectFile] = []
        for path in paths:
            with (extracted_root / path).open("rb") as source:
                saved.append(save_project_file(project, path, source))
        return saved

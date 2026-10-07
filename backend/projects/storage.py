import hashlib
import shutil
import tempfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import BinaryIO

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


def _upload_zip(project: Project, upload: object) -> list[ProjectFile]:
    # Extract one archive with the pipeline safety checks
    with tempfile.TemporaryDirectory(prefix="backend-upload-") as temporary:
        root = Path(temporary)
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

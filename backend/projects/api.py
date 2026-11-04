import os
from pathlib import PurePosixPath
from typing import Annotated
from uuid import UUID

from django.core.files.storage import default_storage
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404
from ninja import File, Router, Status, UploadedFile
from ninja.errors import HttpError

from projects.models import Project, Run
from projects.schemas import (
    ErrorSchema,
    ProjectCreateSchema,
    ProjectSchema,
    ProjectUpdateSchema,
    RunCreateSchema,
    RunSchema,
)
from projects.services import artifact_key, build_review, project_preflight
from projects.storage import (
    delete_prefix,
    delete_project_file,
    delete_project_files,
    save_missing_slot,
    upload_project_files,
    validate_relative_path,
)
from projects.tasks import run_pipeline_task

router = Router()


def _project_payload(project: Project) -> dict[str, object]:
    # Serialize one project and its files
    files: list[dict[str, object]] = []
    for project_file in project.files.all():
        files.append(
            {
                "id": project_file.id,
                "path": project_file.path,
                "size": project_file.size,
                "sha256": project_file.sha256,
                "uploaded_at": project_file.uploaded_at,
            }
        )
    return {
        "id": project.id,
        "name": project.name,
        "created_at": project.created_at,
        "updated_at": project.updated_at,
        "files": files,
    }


def _run_payload(run: Run) -> dict[str, object]:
    # Serialize one pipeline run without task internals
    return {
        "id": run.id,
        "project_id": run.project_id,
        "status": run.status,
        "effort": run.effort,
        "main_file": run.main_file,
        "seed_weak": run.seed_weak,
        "model_provider": run.model_provider,
        "created_at": run.created_at,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "storage_prefix": run.storage_prefix,
        "stop_reason": run.stop_reason,
        "a_score": run.a_score,
        "f_score": run.f_score,
        "input_tokens": run.input_tokens,
        "output_tokens": run.output_tokens,
        "cost_usd": run.cost_usd,
        "error_message": run.error_message,
    }


@router.post("/projects", response={201: ProjectSchema})
def create_project(request, payload: ProjectCreateSchema):
    # Create a named source project
    project = Project.objects.create(name=payload.name.strip())
    return Status(201, _project_payload(project))


@router.get("/projects", response=list[ProjectSchema])
def list_projects(request):
    # List projects with their current files
    values: list[dict[str, object]] = []
    for project in Project.objects.prefetch_related("files"):
        values.append(_project_payload(project))
    return values


@router.get("/projects/{project_id}", response={200: ProjectSchema, 404: ErrorSchema})
def get_project(request, project_id: UUID):
    # Return one project and its uploaded files
    project = get_object_or_404(Project.objects.prefetch_related("files"), id=project_id)
    return _project_payload(project)


@router.patch("/projects/{project_id}", response={200: ProjectSchema, 404: ErrorSchema})
def update_project(request, project_id: UUID, payload: ProjectUpdateSchema):
    # Rename one existing project
    project = get_object_or_404(Project, id=project_id)
    project.name = payload.name.strip()
    project.save(update_fields=["name", "updated_at"])
    return _project_payload(project)


@router.delete("/projects/{project_id}", response={204: None, 404: ErrorSchema})
def delete_project(request, project_id: UUID):
    # Delete one project and its stored files
    project = get_object_or_404(Project.objects.prefetch_related("files", "runs"), id=project_id)
    delete_project_files(project)
    for run in project.runs.all():
        if run.storage_prefix:
            delete_prefix(run.storage_prefix)
    project.delete()
    return HttpResponse(status=204)


@router.post(
    "/projects/{project_id}/upload",
    response={200: ProjectSchema, 400: ErrorSchema, 404: ErrorSchema},
)
def upload_project(
    request,
    project_id: UUID,
    files: Annotated[list[UploadedFile], File(...)],
):
    # Upload a safe zip or multiple individual files
    project = get_object_or_404(Project, id=project_id)
    try:
        upload_project_files(project, files)
    except (OSError, ValueError) as error:
        raise HttpError(400, str(error)) from error
    return _project_payload(project)


@router.put(
    "/projects/{project_id}/files/{path:path}",
    response={200: ProjectSchema, 400: ErrorSchema, 404: ErrorSchema},
)
def put_project_file(
    request,
    project_id: UUID,
    path: str,
    file: Annotated[UploadedFile, File(...)],
):
    # Fill one explicit missing file slot
    project = get_object_or_404(Project, id=project_id)
    try:
        save_missing_slot(project, path, file)
    except (OSError, ValueError) as error:
        raise HttpError(400, str(error)) from error
    return _project_payload(project)


@router.delete(
    "/projects/{project_id}/files/{path:path}",
    response={200: ProjectSchema, 400: ErrorSchema, 404: ErrorSchema},
)
def remove_project_file(request, project_id: UUID, path: str):
    # Remove one uploaded file from a project
    project = get_object_or_404(Project, id=project_id)
    try:
        removed = delete_project_file(project, path)
    except ValueError as error:
        raise HttpError(400, str(error)) from error
    if not removed:
        raise HttpError(404, "File was not found in this project")
    return _project_payload(Project.objects.prefetch_related("files").get(id=project_id))


@router.get(
    "/projects/{project_id}/preflight",
    response={200: dict, 400: ErrorSchema, 404: ErrorSchema},
)
def preflight_project(request, project_id: UUID, main_file: str | None = None):
    # Return main file and dependency readiness
    project = get_object_or_404(Project, id=project_id)
    try:
        if main_file is not None:
            validate_relative_path(main_file)
        return project_preflight(project, main_file)
    except (OSError, ValueError) as error:
        raise HttpError(400, str(error)) from error


@router.get(
    "/projects/{project_id}/runs",
    response={200: list[RunSchema], 404: ErrorSchema},
)
def list_runs(request, project_id: UUID):
    # List one project's runs, newest first
    project = get_object_or_404(Project, id=project_id)
    return [_run_payload(run) for run in project.runs.all()]


@router.post(
    "/projects/{project_id}/runs",
    response={202: RunSchema, 400: ErrorSchema, 404: ErrorSchema},
)
def create_run(request, project_id: UUID, payload: RunCreateSchema):
    # Queue one accessibility remediation run
    project = get_object_or_404(Project, id=project_id)
    if payload.main_file is not None:
        try:
            validate_relative_path(payload.main_file)
        except ValueError as error:
            raise HttpError(400, str(error)) from error
    provider = os.getenv("MODEL_PROVIDER", "fake").strip().lower() or "fake"
    run = Run(
        project=project,
        effort=payload.effort,
        main_file=payload.main_file or "",
        seed_weak=payload.seed_weak,
        model_provider=provider,
    )
    run.storage_prefix = f"runs/{run.id}"
    run.save()
    run_pipeline_task.enqueue(str(run.id))
    run.refresh_from_db()
    return Status(202, _run_payload(run))


@router.get("/runs/{run_id}", response={200: RunSchema, 404: ErrorSchema})
def get_run(request, run_id: UUID):
    # Return run status and summary values
    run = get_object_or_404(Run, id=run_id)
    return _run_payload(run)


@router.get("/runs/{run_id}/review", response={200: dict, 404: ErrorSchema, 409: ErrorSchema})
def get_run_review(request, run_id: UUID):
    # Return review data for one successful run
    run = get_object_or_404(Run, id=run_id)
    if run.status != Run.Status.SUCCEEDED:
        raise HttpError(409, "Review is available after a run succeeds")
    try:
        return build_review(run)
    except (OSError, ValueError) as error:
        raise HttpError(404, "Review artifacts are unavailable") from error


@router.get("/runs/{run_id}/artifact/{path:relpath}")
def download_artifact(request, run_id: UUID, relpath: str):
    # Download one approved artifact from a completed run
    run = get_object_or_404(Run, id=run_id)
    try:
        key = artifact_key(run, relpath)
    except ValueError as error:
        raise HttpError(400, str(error)) from error
    except FileNotFoundError as error:
        raise HttpError(404, "Artifact was not found") from error
    name = PurePosixPath(key).name
    inline = key.endswith(".png")
    return FileResponse(default_storage.open(key, "rb"), as_attachment=not inline, filename=name)

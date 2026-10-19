import json
from decimal import Decimal
from pathlib import Path

from django.tasks import task
from django.utils import timezone

from a11y_pipeline.cli import _model_client
from a11y_pipeline.config import Settings
from a11y_pipeline.runs.folder import RunBlockedError, run_to_folder
from projects.models import Run
from projects.storage import materialize_project, scratch_dir, upload_run_folder

# Source copies are large and reproducible from the project files, so they stay out of storage
SKIPPED_RUN_FOLDERS = ("work/original", "work/marked")


@task
def run_pipeline_task(run_id: str) -> str:
    # Run one queued project through the complete pipeline in a scratch folder
    run = Run.objects.select_related("project").get(id=run_id)
    run.status = Run.Status.RUNNING
    run.started_at = timezone.now()
    run.error_message = ""
    run.save(update_fields=["status", "started_at", "error_message"])
    try:
        with scratch_dir(f"run-{run.id}") as scratch:
            bundle_root = scratch / "bundle"
            output_root = scratch / "output"
            materialize_project(run.project, bundle_root)
            pipeline_settings = Settings()
            client = _model_client(pipeline_settings)
            try:
                completed = run_to_folder(
                    bundle_root,
                    client,
                    pipeline_settings,
                    effort=run.effort,
                    main_file=run.main_file or None,
                    seed_weak_element_id=run.seed_weak,
                    output_root=output_root,
                )
            except RunBlockedError as error:
                upload_run_folder(run.id, error.folder.root, SKIPPED_RUN_FOLDERS)
                _update_run_from_manifest(run, error.folder.root, Run.Status.BLOCKED)
                return str(run.id)
            upload_run_folder(run.id, completed.folder.root, SKIPPED_RUN_FOLDERS)
            _update_completed_run(run, completed.folder.root, completed)
    except Exception as error:
        run.status = Run.Status.FAILED
        run.finished_at = timezone.now()
        run.error_message = f"{type(error).__name__}: Pipeline run failed"
        run.save(update_fields=["status", "finished_at", "error_message"])
        raise
    return str(run.id)


def _update_completed_run(run: Run, root: Path, completed: object) -> None:
    # Persist scores and manifest totals from a completed run
    manifest = _read_manifest(root)
    totals = manifest.get("totals", {})
    run.status = Run.Status.SUCCEEDED
    run.finished_at = timezone.now()
    run.storage_prefix = f"runs/{run.id}"
    run.main_file = manifest.get("inputs", {}).get("main_file", run.main_file)
    run.model_provider = manifest.get("model", {}).get("provider", run.model_provider)
    run.stop_reason = manifest.get("stop_reason") or ""
    run.a_score = completed.stats.accessibility.value
    run.f_score = completed.stats.fidelity.value
    run.input_tokens = int(totals.get("input_tokens", 0))
    run.output_tokens = int(totals.get("output_tokens", 0))
    run.cost_usd = Decimal(str(totals.get("cost_usd", 0)))
    run.save()


def _update_run_from_manifest(run: Run, root: Path, status: str) -> None:
    # Persist safe metadata from a blocked pipeline run
    manifest = _read_manifest(root)
    totals = manifest.get("totals", {})
    run.status = status
    run.finished_at = timezone.now()
    run.storage_prefix = f"runs/{run.id}"
    run.main_file = manifest.get("inputs", {}).get("main_file", run.main_file)
    run.model_provider = manifest.get("model", {}).get("provider", run.model_provider)
    run.stop_reason = manifest.get("stop_reason") or "preflight_blocked"
    run.input_tokens = int(totals.get("input_tokens", 0))
    run.output_tokens = int(totals.get("output_tokens", 0))
    run.cost_usd = Decimal(str(totals.get("cost_usd", 0)))
    run.save()


def _read_manifest(root: Path) -> dict[str, object]:
    # Read one generated manifest without logging its contents
    return json.loads((root / "manifest.json").read_text(encoding="utf-8"))

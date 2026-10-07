import difflib
import json
import re
import subprocess
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from a11y_pipeline.adapters import get_adapter
from a11y_pipeline.capabilities.figure_description import PROMPT_VERSION
from a11y_pipeline.config import Settings
from a11y_pipeline.evaluation.pdf_checks import check_pdf
from a11y_pipeline.ir.models import Candidate, Issue
from a11y_pipeline.ir.serialize import write_document
from a11y_pipeline.models.client import ModelClient
from a11y_pipeline.orchestration.effort import Effort
from a11y_pipeline.orchestration.graph import run_pipeline
from a11y_pipeline.orchestration.state import RunState
from a11y_pipeline.render.pages import render_pages
from a11y_pipeline.render.pixeldiff import compare_pdf_pixels, visual_change_issues
from a11y_pipeline.report.html import write_html_report
from a11y_pipeline.report.stats import ReportStats, build_report_stats
from a11y_pipeline.runs.manifest import build_manifest, write_manifest
from a11y_pipeline.synthesis.tagger import tag_pdf

RUN_ID_PATTERN = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{8}$")


@dataclass(frozen=True)
class RunFolder:
    root: Path

    @property
    def run_id(self) -> str:
        # Return the timestamped run identifier
        return self.root.name

    @property
    def manifest_path(self) -> Path:
        # Return the manifest output path
        return self.root / "manifest.json"

    @property
    def telemetry_path(self) -> Path:
        # Return the telemetry output path
        return self.root / "telemetry.jsonl"

    @property
    def output_dir(self) -> Path:
        # Return the final output directory
        return self.root / "output"

    @property
    def report_path(self) -> Path:
        # Return the HTML report output path
        return self.root / "report.html"


@dataclass(frozen=True)
class CompletedRun:
    folder: RunFolder
    state: RunState
    stats: ReportStats


class RunBlockedError(RuntimeError):
    def __init__(self, folder: RunFolder, state: RunState) -> None:
        # Preserve blocked run details for the command line
        super().__init__("Preflight blocked the run")
        self.folder = folder
        self.state = state


def create_run_folder(
    output_root: Path,
    *,
    timestamp: datetime | None = None,
    short_id: str | None = None,
) -> RunFolder:
    # Create the complete fixed run directory layout
    moment = timestamp or datetime.now().astimezone()
    identifier = short_id or uuid4().hex[:8]
    run_id = moment.strftime("%Y%m%d-%H%M%S") + "-" + identifier
    if RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise ValueError("Run identifier must use timestamp and eight lowercase hex characters")
    root = output_root.expanduser().resolve() / run_id
    root.mkdir(parents=True, exist_ok=False)
    directories = [
        root / "candidates",
        root / "work",
        root / "pages",
        root / "crops",
        root / "output",
    ]
    for directory in directories:
        directory.mkdir()
    return RunFolder(root=root)


def write_run_snapshots(folder: RunFolder, state: RunState) -> None:
    # Write stable base candidate and final snapshots
    if state.base_ir is None:
        raise ValueError("A completed run must have a base IR")
    if state.final_ir is None:
        raise ValueError("A completed run must have a final IR")
    write_document(state.base_ir, folder.root / "ir_base.json")
    write_document(state.final_ir, folder.root / "ir_final.json")
    for candidate in state.candidates:
        path = folder.root / "candidates" / f"{candidate.candidate_id}.json"
        payload = candidate.model_dump(mode="json")
        text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        path.write_text(text, encoding="utf-8")


def archive_project(project_root: Path, output_path: Path) -> Path:
    # Create a stable source project zip
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        files: list[Path] = []
        for path in project_root.rglob("*"):
            if path.is_file():
                files.append(path)
        files.sort()
        for path in files:
            relative = path.relative_to(project_root).as_posix()
            archive.write(path, relative)
    return output_path


def run_to_folder(
    input_path: Path,
    model_client: ModelClient,
    settings: Settings,
    *,
    effort: Effort = "medium",
    main_file: str | None = None,
    seed_weak_element_id: str | None = None,
    output_root: Path | None = None,
) -> CompletedRun:
    # Run the complete deterministic pipeline and materialize outputs
    destination = output_root or settings.runs_dir
    folder = create_run_folder(destination)
    folder.telemetry_path.touch()
    state = run_pipeline(
        model_client=model_client,
        effort=effort,
        settings=settings,
        run_id=folder.run_id,
        telemetry_path=folder.telemetry_path,
        input_path=input_path,
        main_file=main_file,
        seed_weak_element_id=seed_weak_element_id,
    )
    if state.blocked or state.bundle is None or state.final_ir is None:
        if state.bundle is not None:
            manifest = build_manifest(
                state,
                state.bundle,
                input_path,
                [PROMPT_VERSION],
            )
            write_manifest(folder.manifest_path, manifest)
        raise RunBlockedError(folder, state)
    return _materialize_completed_run(folder, state, input_path)


def _materialize_completed_run(
    folder: RunFolder,
    state: RunState,
    input_path: Path,
) -> CompletedRun:
    # Build tagged PDF source archive snapshots report and manifest
    if state.bundle is None or state.final_ir is None:
        raise ValueError("Completed run state is missing its bundle or final IR")
    if state.original_pdf is None or state.marked_pdf is None:
        raise ValueError("Completed run state is missing compiled PDFs")
    adapter = get_adapter(state.adapter_name)
    tagged_path = folder.output_dir / "tagged.pdf"
    tagging = tag_pdf(state.marked_pdf, state.final_ir, tagged_path)
    pdf_checks = check_pdf(tagged_path, state.final_ir)
    tagged_pixels = compare_pdf_pixels(state.original_pdf, tagged_path)
    output_issues = list(tagging.issues)
    output_issues.extend(pdf_checks.issues)
    output_issues.extend(visual_change_issues(state.final_ir, tagged_pixels))
    written = adapter.write_back(
        state.bundle,
        state.final_ir,
        folder.output_dir / "updated_project",
        folder.output_dir / "changes.diff",
        folder.root / "work" / "updated_verify",
        state.original_pdf,
        state.config.compile_timeout_seconds,
    )
    output_issues.extend(written.issues)
    archive_project(
        written.project_root,
        folder.output_dir / "updated_project.zip",
    )
    page_images = render_pages(tagged_path, folder.root / "pages", dpi=110)
    selected = _selected_candidate(state)
    combined_issues = _combined_issues(state, selected, output_issues)
    state.issues = combined_issues
    state.final_ir.issues = combined_issues
    stats = build_report_stats(
        state.final_ir,
        selected,
        folder.telemetry_path,
        state.stop_reason or "unknown",
        pdf_checks=pdf_checks,
        pixel_check=tagged_pixels,
        text_similarity=_pdf_text_similarity(state.original_pdf, tagged_path),
        issues=combined_issues,
    )
    write_run_snapshots(folder, state)
    _write_operations(folder, tagging.operations, written.operations)
    write_html_report(
        folder.report_path,
        folder.root,
        state.final_ir,
        state.candidates,
        state.selected_candidate_id,
        combined_issues,
        stats,
        page_images,
        tagged_path,
    )
    manifest = build_manifest(
        state,
        state.bundle,
        input_path,
        [PROMPT_VERSION],
    )
    write_manifest(folder.manifest_path, manifest)
    return CompletedRun(folder=folder, state=state, stats=stats)


def _selected_candidate(state: RunState) -> Candidate:
    # Return the selected candidate from completed state
    for candidate in state.candidates:
        if candidate.candidate_id == state.selected_candidate_id:
            return candidate
    raise ValueError("Completed run has no selected candidate")


def _combined_issues(
    state: RunState,
    selected: Candidate,
    output_issues: list[Issue],
) -> list[Issue]:
    # Combine and deduplicate findings from every pipeline phase
    values: list[Issue] = []
    values.extend(state.issues)
    values.extend(selected.issues)
    values.extend(selected.vetoes)
    values.extend(output_issues)
    unique: list[Issue] = []
    seen: set[str] = set()
    for issue in values:
        key = issue.model_dump_json(exclude_none=False)
        if key in seen:
            continue
        seen.add(key)
        unique.append(issue)
    return unique


def _write_operations(
    folder: RunFolder,
    tagging_operations: list[object],
    writing_operations: list[object],
) -> Path:
    # Record deterministic synthesis operations
    records: list[object] = []
    for operation in tagging_operations:
        records.append(operation.model_dump(mode="json"))
    for operation in writing_operations:
        records.append(operation.model_dump(mode="json"))
    path = folder.output_dir / "operations.json"
    path.write_text(
        json.dumps(records, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _pdf_text_similarity(original_pdf: Path, tagged_pdf: Path) -> float:
    # Compare normalized extracted text from original and tagged PDFs
    original = _extract_pdf_text(original_pdf)
    tagged = _extract_pdf_text(tagged_pdf)
    return difflib.SequenceMatcher(None, original, tagged).ratio() * 100.0


def _extract_pdf_text(path: Path) -> str:
    # Extract normalized page text with poppler
    completed = subprocess.run(
        ["pdftotext", "-layout", str(path), "-"],
        capture_output=True,
        check=False,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or "pdftotext failed"
        raise RuntimeError(detail)
    return " ".join(completed.stdout.split())

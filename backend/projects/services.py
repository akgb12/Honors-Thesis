from pathlib import PurePosixPath
from typing import Any

from django.core.files.storage import default_storage

from a11y_pipeline.adapters import get_adapter
from a11y_pipeline.bundle.bundle import Bundle
from projects.models import Project, Run
from projects.storage import (
    list_run_files,
    materialize_project,
    read_run_json,
    scratch_dir,
    validate_relative_path,
)

DOWNLOADABLE_ARTIFACTS = {
    "output/tagged.pdf",
    "output/updated_project.zip",
    "report.html",
}


def project_preflight(project: Project, main_file: str | None = None) -> dict[str, object]:
    # Run pipeline preflight against files from Django storage
    with scratch_dir("preflight") as scratch:
        bundle_root = scratch / "bundle"
        materialize_project(project, bundle_root)
        bundle = Bundle.from_path(bundle_root, main_file)
        result = get_adapter("tex-beamer").preflight(bundle)
        issues: list[dict[str, object]] = []
        for issue in result.issues:
            issues.append(
                {
                    "code": issue.code,
                    "severity": issue.severity,
                    "message": issue.message,
                    "source_file": issue.source_file,
                    "line": issue.line,
                    "dependency": issue.dependency,
                }
            )
        return {
            "ok": result.ok and not result.missing_images,
            "main_file": bundle.main_file,
            "missing_images": result.missing_images,
            "critical_blockers": result.missing_critical,
            "issues": issues,
        }


def artifact_key(run: Run, relative_path: str) -> str:
    # Resolve one approved downloadable run artifact to its storage key
    relative = validate_relative_path(relative_path)
    allowed = relative in DOWNLOADABLE_ARTIFACTS
    path = PurePosixPath(relative)
    if len(path.parts) == 2 and path.parts[0] == "pages" and path.suffix.lower() == ".png":
        allowed = True
    if not allowed:
        raise ValueError("Artifact path is not downloadable")
    if not run.storage_prefix:
        raise FileNotFoundError(relative)
    key = f"{validate_relative_path(run.storage_prefix)}/{relative}"
    if not default_storage.exists(key):
        raise FileNotFoundError(relative)
    return key


def build_review(run: Run) -> dict[str, object]:
    # Build the review payload from final run artifacts in storage
    prefix = validate_relative_path(run.storage_prefix)
    ir = read_run_json(prefix, "ir_final.json")
    issues_by_element: dict[str, list[dict[str, object]]] = {}
    document_issues: list[dict[str, object]] = []
    for issue in ir.get("issues", []):
        element_id = issue.get("element_id")
        if element_id:
            issues_by_element.setdefault(element_id, []).append(issue)
        else:
            document_issues.append(issue)
    elements: list[dict[str, object]] = []
    for element_id, element in ir["elements"].items():
        render = element["render"]
        accessibility = element["accessibility"]
        elements.append(
            {
                "id": element_id,
                "type": element["semantic_type"],
                "role": accessibility.get("role"),
                "status": accessibility["status"],
                "pages": render["pages"],
                "bbox": render.get("bbox"),
                "anchor": render.get("anchor"),
                "alt": accessibility.get("alt_text"),
                "extended_description": accessibility.get("extended_description"),
                "issues": issues_by_element.get(element_id, []),
            }
        )
    history: list[dict[str, object]] = []
    for name in list_run_files(prefix, "candidates"):
        if name.endswith(".json"):
            history.append(read_run_json(prefix, f"candidates/{name}"))
    return {
        "run_id": str(run.id),
        "containers": ir["containers"],
        "elements": elements,
        "pages": _page_payloads(run, read_run_json(prefix, "manifest.json")),
        "scores": {"accessibility": run.a_score, "fidelity": run.f_score},
        "stop_reason": run.stop_reason,
        "round_history": history,
        "issues": document_issues,
    }


def _page_payloads(run: Run, manifest: dict[str, Any]) -> list[dict[str, object]]:
    # Pair manifest page sizes with artifact URLs for the rendered images
    pages: list[dict[str, object]] = []
    for page in manifest.get("pages", []):
        pages.append(
            {
                "number": page["number"],
                "image_url": f"/api/runs/{run.id}/artifact/{page['image']}",
                "width_points": page["width_points"],
                "height_points": page["height_points"],
            }
        )
    return pages

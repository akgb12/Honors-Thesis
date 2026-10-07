import json
import tempfile
from pathlib import Path, PurePosixPath

import pikepdf
from django.conf import settings

from a11y_pipeline.adapters import get_adapter
from a11y_pipeline.bundle.bundle import Bundle
from projects.models import Project, Run
from projects.storage import materialize_project, validate_relative_path

DOWNLOADABLE_ARTIFACTS = {
    "output/tagged.pdf",
    "output/updated_project.zip",
    "report.html",
}


def project_preflight(project: Project, main_file: str | None = None) -> dict[str, object]:
    # Run pipeline preflight against files from Django storage
    with tempfile.TemporaryDirectory(prefix="backend-preflight-") as temporary:
        bundle_root = Path(temporary) / "bundle"
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


def run_root(run: Run) -> Path:
    # Resolve a run directory without allowing storage escapes
    relative = validate_relative_path(run.run_dir)
    media_root = Path(settings.MEDIA_ROOT).resolve()
    root = (media_root / relative).resolve()
    if not root.is_relative_to(media_root):
        raise ValueError("Run directory escapes media storage")
    return root


def artifact_path(run: Run, relative_path: str) -> Path:
    # Resolve one approved downloadable run artifact
    relative = validate_relative_path(relative_path)
    allowed = relative in DOWNLOADABLE_ARTIFACTS
    path = PurePosixPath(relative)
    if len(path.parts) == 2 and path.parts[0] == "pages" and path.suffix.lower() == ".png":
        allowed = True
    if not allowed:
        raise ValueError("Artifact path is not downloadable")
    root = run_root(run)
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError("Artifact path escapes the run directory")
    if not candidate.is_file():
        raise FileNotFoundError(relative)
    return candidate


def build_review(run: Run) -> dict[str, object]:
    # Build the review payload from final run artifacts
    root = run_root(run)
    ir = json.loads((root / "ir_final.json").read_text(encoding="utf-8"))
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
    for candidate_path in sorted((root / "candidates").glob("*.json")):
        history.append(json.loads(candidate_path.read_text(encoding="utf-8")))
    pages = _page_payloads(run, root)
    return {
        "run_id": str(run.id),
        "containers": ir["containers"],
        "elements": elements,
        "pages": pages,
        "scores": {"accessibility": run.a_score, "fidelity": run.f_score},
        "stop_reason": run.stop_reason,
        "round_history": history,
        "issues": document_issues,
    }


def _page_payloads(run: Run, root: Path) -> list[dict[str, object]]:
    # Read page dimensions and pair them with rendered images
    images = sorted((root / "pages").glob("*.png"))
    pages: list[dict[str, object]] = []
    with pikepdf.open(root / "output" / "tagged.pdf") as pdf:
        for index, page in enumerate(pdf.pages):
            media_box = page.MediaBox
            image_name = images[index].name
            pages.append(
                {
                    "number": index + 1,
                    "image_url": (f"/api/runs/{run.id}/artifact/pages/{image_name}"),
                    "width_points": float(media_box[2]) - float(media_box[0]),
                    "height_points": float(media_box[3]) - float(media_box[1]),
                }
            )
    return pages

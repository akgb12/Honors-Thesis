from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from a11y_pipeline.ir.models import Candidate, DocumentIR, Element, Issue
from a11y_pipeline.render.crop import page_box_points
from a11y_pipeline.report.stats import ReportStats

SEVERITY_ORDER = ("veto", "error", "warning", "info")


def write_html_report(
    output_path: Path,
    run_root: Path,
    ir: DocumentIR,
    candidates: list[Candidate],
    selected_candidate_id: str | None,
    issues: list[Issue],
    stats: ReportStats,
    page_images: list[Path],
    pdf_path: Path,
) -> Path:
    # Render the self contained read only accessibility report
    environment = Environment(
        loader=FileSystemLoader(Path(__file__).parent / "templates"),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = environment.get_template("report.html.j2")
    context = {
        "document_title": ir.metadata.get("title", "Untitled document"),
        "run_id": run_root.name,
        "stats": stats,
        "status_counts": _sorted_counts(stats.status_counts),
        "pages": _page_records(run_root, ir, page_images, pdf_path),
        "issue_groups": _issue_groups(issues),
        "elements": _element_records(ir),
        "candidates": _candidate_records(candidates, selected_candidate_id),
        "not_handled": _not_handled_records(ir),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(template.render(**context), encoding="utf-8")
    return output_path


def _sorted_counts(counts: dict[str, int]) -> list[dict[str, Any]]:
    # Sort status counts for stable report output
    records: list[dict[str, Any]] = []
    for status in sorted(counts):
        records.append({"status": status, "count": counts[status]})
    return records


def _page_records(
    run_root: Path,
    ir: DocumentIR,
    page_images: list[Path],
    pdf_path: Path,
) -> list[dict[str, Any]]:
    # Build page image and positioned box records
    records: list[dict[str, Any]] = []
    for index, image_path in enumerate(page_images, start=1):
        media_box = page_box_points(pdf_path, index)
        boxes: list[dict[str, Any]] = []
        for element in ir.elements.values():
            if index not in element.render.pages:
                continue
            position = _box_position(element, media_box)
            if position is None:
                continue
            boxes.append(
                {
                    "id": element.id,
                    "status": element.accessibility.status,
                    "role": element.accessibility.role or "",
                    "type": element.semantic_type,
                    "alt_text": element.accessibility.alt_text or "",
                    "left": position[0],
                    "top": position[1],
                    "width": position[2],
                    "height": position[3],
                }
            )
        relative = image_path.relative_to(run_root).as_posix()
        records.append({"number": index, "image": relative, "boxes": boxes})
    return records


def _box_position(
    element: Element,
    page_box: tuple[float, float, float, float],
) -> tuple[float, float, float, float] | None:
    # Convert mapped PDF coordinates into page percentages
    page_x0, page_y0, page_x1, page_y1 = page_box
    page_width = page_x1 - page_x0
    page_height = page_y1 - page_y0
    if page_width <= 0 or page_height <= 0:
        return None
    if element.render.bbox is not None:
        x0, y0, x1, y1 = element.render.bbox
        left = (x0 - page_x0) / page_width * 100.0
        top = (page_y1 - y1) / page_height * 100.0
        width = (x1 - x0) / page_width * 100.0
        height = (y1 - y0) / page_height * 100.0
        return _clamp_box(left, top, width, height)
    if element.render.anchor is not None:
        x, y = element.render.anchor
        left = (x - page_x0) / page_width * 100.0 - 0.75
        top = (page_y1 - y) / page_height * 100.0 - 0.75
        return _clamp_box(left, top, 1.5, 1.5)
    return None


def _clamp_box(
    left: float,
    top: float,
    width: float,
    height: float,
) -> tuple[float, float, float, float]:
    # Keep report boxes inside their page image
    safe_left = max(0.0, min(left, 99.0))
    safe_top = max(0.0, min(top, 99.0))
    safe_width = max(1.0, min(width, 100.0 - safe_left))
    safe_height = max(1.0, min(height, 100.0 - safe_top))
    return safe_left, safe_top, safe_width, safe_height


def _issue_groups(issues: list[Issue]) -> list[dict[str, Any]]:
    # Group issues by severity in review order
    records: list[dict[str, Any]] = []
    for severity in SEVERITY_ORDER:
        values: list[Issue] = []
        for issue in issues:
            if issue.severity == severity:
                values.append(issue)
        records.append({"severity": severity, "issues": values})
    return records


def _element_records(ir: DocumentIR) -> list[dict[str, Any]]:
    # Flatten elements into report table records
    records: list[dict[str, Any]] = []
    for element in ir.elements.values():
        pages = ""
        if element.render.pages:
            page_values: list[str] = []
            for page in element.render.pages:
                page_values.append(str(page))
            pages = ", ".join(page_values)
        records.append(
            {
                "id": element.id,
                "type": element.semantic_type,
                "role": element.accessibility.role or "",
                "status": element.accessibility.status,
                "source": (
                    f"{element.source.file}:{element.source.line_start}–{element.source.line_end}"
                ),
                "pages": pages,
                "alt_text": element.accessibility.alt_text or "",
            }
        )
    return records


def _candidate_records(
    candidates: list[Candidate],
    selected_candidate_id: str | None,
) -> list[dict[str, Any]]:
    # Flatten candidate round and score history
    records: list[dict[str, Any]] = []
    for candidate in candidates:
        records.append(
            {
                "id": candidate.candidate_id,
                "round": candidate.round,
                "score_a": candidate.scores.get("A"),
                "score_f": candidate.scores.get("F"),
                "patches": len(candidate.patches),
                "vetoes": len(candidate.vetoes),
                "selected": candidate.candidate_id == selected_candidate_id,
            }
        )
    return records


def _not_handled_records(ir: DocumentIR) -> list[Element]:
    # Collect unknown and explicitly unhandled elements
    records: list[Element] = []
    for element in ir.elements.values():
        if element.semantic_type == "unknown":
            records.append(element)
            continue
        if element.accessibility.status == "not_handled":
            records.append(element)
    return records

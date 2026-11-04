from dataclasses import dataclass
from pathlib import Path

from a11y_pipeline.evaluation.pdf_checks import PdfCheckResult
from a11y_pipeline.evaluation.scores import IndexScore, compute_preliminary_scores
from a11y_pipeline.ir.models import Candidate, DocumentIR, Issue
from a11y_pipeline.render.pixeldiff import PixelCheck
from a11y_pipeline.runs.manifest import telemetry_totals


@dataclass(frozen=True)
class ReportStats:
    accessibility: IndexScore
    fidelity: IndexScore
    status_counts: dict[str, int]
    input_tokens: int
    output_tokens: int
    cost_usd: float
    model_calls: int
    stop_reason: str


def build_report_stats(
    ir: DocumentIR,
    selected: Candidate,
    telemetry_path: Path,
    stop_reason: str,
    *,
    pdf_checks: PdfCheckResult | None = None,
    pixel_check: PixelCheck | None = None,
    text_similarity: float | None = None,
    issues: list[Issue] | None = None,
) -> ReportStats:
    # Compute preliminary report indices and run totals
    all_issues = issues or []
    accessibility_metrics: dict[str, float | None] = {
        "T": _check_metric(pdf_checks, "structure_completeness"),
        "R": _check_metric(pdf_checks, "structure_completeness"),
        "H": _hierarchy_metric(ir),
        "I": selected.scores.get("A"),
        "B": None,
        "M": _formula_metric(ir),
        "D": _metadata_metric(pdf_checks),
        "C": _checker_metric(pdf_checks),
    }
    fidelity_metrics: dict[str, float | None] = {
        "X": text_similarity,
        "E": _formula_metric(ir),
        "G": _figure_preservation_metric(ir, pixel_check),
        "B_f": None,
        "S": _check_metric(pdf_checks, "structure_completeness"),
        "Q_s": _semantic_consistency_metric(all_issues),
        "O": _output_completeness_metric(pdf_checks),
    }
    scores = compute_preliminary_scores(accessibility_metrics, fidelity_metrics)
    counts: dict[str, int] = {}
    for element in ir.elements.values():
        status = element.accessibility.status
        counts[status] = counts.get(status, 0) + 1
    usage = telemetry_totals(telemetry_path)
    return ReportStats(
        accessibility=scores.accessibility,
        fidelity=scores.fidelity,
        status_counts=counts,
        input_tokens=int(usage["input_tokens"]),
        output_tokens=int(usage["output_tokens"]),
        cost_usd=float(usage["cost_usd"]),
        model_calls=int(usage["calls"]),
        stop_reason=stop_reason,
    )


def _check_metric(result: PdfCheckResult | None, name: str) -> float | None:
    # Convert one available PDF check into a percentage
    if result is None or name not in result.checks:
        return None
    if result.checks[name]:
        return 100.0
    return 0.0


def _hierarchy_metric(ir: DocumentIR) -> float:
    # Score required heading and list hierarchy rules
    violations = 0
    has_h1 = False
    for element in ir.elements.values():
        if element.accessibility.role == "H1":
            has_h1 = True
        if element.semantic_type == "list":
            has_item = False
            for child_id in element.child_ids:
                child = ir.elements.get(child_id)
                if child is not None and child.semantic_type == "list_item":
                    has_item = True
            if not has_item:
                violations += 1
        if element.semantic_type == "list_item":
            parent = ir.elements.get(element.parent_id or "")
            if parent is None or parent.semantic_type != "list":
                violations += 1
    if not has_h1 and ir.metadata.get("title", "").strip():
        violations += 1
    for container in ir.containers:
        if container.kind != "slide":
            continue
        if container.title_element_id is None:
            violations += 1
    return max(0.0, 100.0 - violations * 25.0)


def _formula_metric(ir: DocumentIR) -> float | None:
    # Score formulas with exact source alternatives
    total = 0
    passed = 0
    for element in ir.elements.values():
        if element.semantic_type != "formula":
            continue
        total += 1
        if element.fidelity.signature:
            passed += 1
    if total == 0:
        return None
    return passed / total * 100.0


def _metadata_metric(result: PdfCheckResult | None) -> float | None:
    # Score the four required document metadata checks
    if result is None:
        return None
    names = ["language", "info_title", "xmp_title", "display_document_title"]
    passed = 0
    for name in names:
        if result.checks.get(name, False):
            passed += 1
    return passed / len(names) * 100.0


def _checker_metric(result: PdfCheckResult | None) -> float | None:
    # Score all available deterministic PDF checks
    if result is None or not result.checks:
        return None
    passed = 0
    for value in result.checks.values():
        if value:
            passed += 1
    return passed / len(result.checks) * 100.0


def _figure_preservation_metric(
    ir: DocumentIR,
    pixel_check: PixelCheck | None,
) -> float | None:
    # Score mapped figures when output pixels remain unchanged
    figures = 0
    mapped = 0
    for element in ir.elements.values():
        if element.semantic_type != "figure":
            continue
        figures += 1
        if element.render.pages:
            mapped += 1
    if figures == 0:
        return None
    if pixel_check is None or not pixel_check.identical:
        return 0.0
    return mapped / figures * 100.0


def _semantic_consistency_metric(issues: list[Issue]) -> float | None:
    # Apply only deterministic source contradiction findings
    for issue in issues:
        if issue.code == "source_contradiction":
            return 0.0
    return None


def _output_completeness_metric(result: PdfCheckResult | None) -> float | None:
    # Score marked text showing operations across pages
    if result is None:
        return None
    total = 0
    unmarked = 0
    for page in result.pages:
        total += page.total_text_operators
        unmarked += page.unmarked_text_operators
    if total == 0:
        return None
    return max(0.0, (1.0 - unmarked / total) * 100.0)

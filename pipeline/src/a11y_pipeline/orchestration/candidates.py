from dataclasses import dataclass

from a11y_pipeline.evaluation.concepts import evaluate_coverage
from a11y_pipeline.evaluation.scores import figure_accessibility_score
from a11y_pipeline.evaluation.signals import evaluate_signals
from a11y_pipeline.evaluation.vetoes import evaluate_vetoes
from a11y_pipeline.ir.models import Candidate, DocumentIR, Issue
from a11y_pipeline.ir.patches import apply_patches


@dataclass(frozen=True)
class CandidateEvaluation:
    candidate: Candidate
    document: DocumentIR
    failing_element_ids: list[str]


def evaluate_candidate(
    base_ir: DocumentIR,
    candidate: Candidate,
    coverage_threshold: float,
    nearby_text_by_element: dict[str, list[str]] | None = None,
    visible_labels_by_element: dict[str, list[str]] | None = None,
) -> CandidateEvaluation:
    # Evaluate one cumulative candidate against the frozen base
    document = apply_patches(base_ir, candidate.patches)
    nearby = nearby_text_by_element or {}
    visible = visible_labels_by_element or {}
    issues: list[Issue] = []
    figure_scores: list[float] = []
    coverage_by_element: dict[str, float | None] = {}
    for element in document.elements.values():
        if element.semantic_type != "figure":
            continue
        coverage = evaluate_coverage(
            element.accessibility.alt_text,
            element.fidelity.required_concepts,
        )
        signals = evaluate_signals(
            element.id,
            element.accessibility.alt_text,
            element.fidelity.required_concepts,
            nearby.get(element.id, []),
        )
        issues.extend(signals.issues)
        coverage_by_element[element.id] = coverage.coverage
        figure_scores.append(
            figure_accessibility_score(
                alt_present=bool((element.accessibility.alt_text or "").strip()),
                coverage=coverage.coverage,
                warning_count=signals.warning_count,
                missing_asset=element.accessibility.status == "missing_asset",
            )
        )
        if coverage.applicable and coverage.coverage is not None:
            if coverage.coverage < coverage_threshold:
                issues.append(
                    Issue(
                        element_id=element.id,
                        code="alt_low_coverage",
                        severity="error",
                        message="Figure alternative text is below the concept coverage threshold",
                        details={
                            "coverage": coverage.coverage,
                            "threshold": coverage_threshold,
                            "missing": coverage.missing,
                        },
                    )
                )
    vetoes = evaluate_vetoes(base_ir, document, visible)
    failing = _failing_elements(document, coverage_by_element, coverage_threshold, vetoes)
    score_a = 100.0
    if figure_scores:
        score_a = sum(figure_scores) / len(figure_scores)
    score_f = 100.0
    if vetoes:
        score_f = 0.0
    evaluated = candidate.model_copy(deep=True)
    evaluated.scores = {"A": score_a, "F": score_f}
    evaluated.vetoes = vetoes
    evaluated.issues = issues
    return CandidateEvaluation(
        candidate=evaluated,
        document=document,
        failing_element_ids=failing,
    )


def _failing_elements(
    document: DocumentIR,
    coverage_by_element: dict[str, float | None],
    threshold: float,
    vetoes: list[Issue],
) -> list[str]:
    # Find figures eligible for focused repair
    vetoed_ids: set[str] = set()
    for veto in vetoes:
        if veto.element_id is not None:
            vetoed_ids.add(veto.element_id)
    failing: list[str] = []
    for element in document.elements.values():
        if element.semantic_type != "figure":
            continue
        coverage = coverage_by_element.get(element.id)
        low_coverage = coverage is not None and coverage < threshold
        failed = element.accessibility.status == "failed"
        if low_coverage or failed or element.id in vetoed_ids:
            failing.append(element.id)
    return failing

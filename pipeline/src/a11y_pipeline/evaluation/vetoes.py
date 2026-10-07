import re

from a11y_pipeline.evaluation.concepts import NUMBER_WORDS, normalize_text
from a11y_pipeline.ir.models import DocumentIR, Element, Issue


def figure_contradiction_veto(
    element: Element,
    visible_labels: list[str],
) -> Issue | None:
    # Detect supported source contradictions in figure text
    alt_text = element.accessibility.alt_text or ""
    for concept in element.fidelity.required_concepts:
        if not concept.startswith("sequence:"):
            continue
        parts = concept.split(":", 2)
        if len(parts) != 3:
            continue
        try:
            expected = int(parts[1])
        except ValueError:
            continue
        stated = _sequence_counts(alt_text, parts[2])
        for count in stated:
            if count != expected:
                return Issue(
                    element_id=element.id,
                    code="contradicts_source",
                    severity="veto",
                    message="Figure alternative text states a conflicting sequence count",
                    details={"expected": expected, "stated": count, "stem": parts[2]},
                )
    unknown = _unknown_quoted_label(alt_text, visible_labels)
    if unknown is not None:
        return Issue(
            element_id=element.id,
            code="contradicts_source",
            severity="veto",
            message="Figure alternative text quotes a label not visible in the figure",
            details={"quoted_label": unknown, "visible_labels": visible_labels},
        )
    return None


def formula_fidelity_vetoes(
    source_ir: DocumentIR,
    candidate_ir: DocumentIR,
) -> list[Issue]:
    # Detect formulas that no longer match their source
    issues: list[Issue] = []
    for element_id, source in source_ir.elements.items():
        if source.semantic_type != "formula":
            continue
        candidate = candidate_ir.elements.get(element_id)
        candidate_signature = None
        if candidate is not None:
            candidate_signature = candidate.fidelity.signature
        if candidate_signature == source.fidelity.signature:
            continue
        issues.append(
            Issue(
                element_id=element_id,
                code="formula_changed",
                severity="veto",
                message="Formula fidelity signature no longer matches the source",
                details={
                    "source_signature": source.fidelity.signature,
                    "candidate_signature": candidate_signature,
                },
            )
        )
    return issues


def evaluate_vetoes(
    source_ir: DocumentIR,
    candidate_ir: DocumentIR,
    visible_labels_by_element: dict[str, list[str]] | None = None,
    pdf_issues: list[Issue] | None = None,
    visual_issues: list[Issue] | None = None,
) -> list[Issue]:
    # Collect the four Mark 1 veto classes
    vetoes = formula_fidelity_vetoes(source_ir, candidate_ir)
    labels_by_element = visible_labels_by_element or {}
    for element in candidate_ir.elements.values():
        if element.semantic_type != "figure":
            continue
        issue = figure_contradiction_veto(
            element,
            labels_by_element.get(element.id, []),
        )
        if issue is not None:
            vetoes.append(issue)
    for issue in pdf_issues or []:
        if issue.code == "structure_content_missing" or issue.severity == "veto":
            vetoes.append(issue)
    for issue in visual_issues or []:
        if issue.code == "visual_change" or issue.severity == "veto":
            vetoes.append(issue)
    return _unique_vetoes(vetoes)


def _sequence_counts(text: str, stem: str) -> list[int]:
    # Find counts stated next to a sequence stem
    normalized = normalize_text(text)
    normalized_stem = normalize_text(stem)
    stems = [normalized_stem]
    if normalized_stem.endswith("s"):
        stems.append(normalized_stem[:-1])
    else:
        stems.append(normalized_stem + "s")
    number_forms: dict[str, int] = {}
    for number in range(0, 21):
        number_forms[str(number)] = number
        number_forms[NUMBER_WORDS[number]] = number
    found: list[int] = []
    for form, number in number_forms.items():
        for candidate_stem in stems:
            if not candidate_stem:
                continue
            first = (
                rf"(?<!\w){re.escape(form)}(?!\w)"
                rf"(?:\W+\w+){{0,2}}\W+{re.escape(candidate_stem)}(?!\w)"
            )
            second = (
                rf"(?<!\w){re.escape(candidate_stem)}(?!\w)"
                rf"(?:\W+\w+){{0,2}}\W+{re.escape(form)}(?!\w)"
            )
            first_found = re.search(first, normalized) is not None
            second_found = re.search(second, normalized) is not None
            if first_found or second_found:
                if number not in found:
                    found.append(number)
    return found


def _unknown_quoted_label(text: str, visible_labels: list[str]) -> str | None:
    # Find a quoted label absent from visible source labels
    visible: set[str] = set()
    for label in visible_labels:
        visible.add(normalize_text(label))
    pattern = re.compile(r"""["“”']([^"“”']+)["“”']""")
    for match in pattern.finditer(text):
        quoted = re.sub(r"\s+", " ", match.group(1)).strip()
        if not quoted or len(quoted.split()) > 8:
            continue
        if re.search(r"[A-Za-z0-9]", quoted) is None:
            continue
        if normalize_text(quoted) not in visible:
            return quoted
    return None


def _unique_vetoes(issues: list[Issue]) -> list[Issue]:
    # Remove duplicate veto findings in stable order
    result: list[Issue] = []
    seen: set[tuple[str | None, str, str]] = set()
    for issue in issues:
        key = (issue.element_id, issue.code, issue.message)
        if key not in seen:
            result.append(issue)
            seen.add(key)
    return result

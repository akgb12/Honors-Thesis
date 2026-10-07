import re
from dataclasses import dataclass, field

from a11y_pipeline.ir.models import Element, Issue

NUMBER_WORDS = {
    0: "zero",
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
    11: "eleven",
    12: "twelve",
    13: "thirteen",
    14: "fourteen",
    15: "fifteen",
    16: "sixteen",
    17: "seventeen",
    18: "eighteen",
    19: "nineteen",
    20: "twenty",
}


@dataclass(frozen=True)
class ConceptSet:
    required: list[str]
    excluded: list[str]
    visible_labels: list[str]
    hidden_labels: list[str]
    issues: list[Issue] = field(default_factory=list)


@dataclass(frozen=True)
class CoverageResult:
    coverage: float | None
    matched: list[str]
    missing: list[str]
    applicable: bool


def normalize_text(value: str) -> str:
    # Normalize text for deterministic matching
    return re.sub(r"\s+", " ", value).strip().casefold()


def infer_tikz_labels(source: str, parsed_labels: list[str] | None = None) -> list[str]:
    # Expand static and supported foreach node labels
    labels: list[str] = []
    static_labels: list[str] = []
    if parsed_labels is not None:
        for parsed in parsed_labels:
            cleaned = _clean_tikz_label(parsed)
            if cleaned and not re.search(r"\\[A-Za-z@]+", cleaned):
                _append_unique(static_labels, cleaned)
    for variable, values, body in _foreach_blocks(source):
        assignments = _foreach_assignments(body, variable)
        templates = _node_label_templates(body)
        for value in values:
            replacements: dict[str, int] = {variable: value}
            for macro, expression in assignments.items():
                evaluated = _evaluate_foreach_expression(expression, variable, value)
                if evaluated is not None:
                    replacements[macro] = evaluated
            for template in templates:
                expanded = template
                for macro, replacement in replacements.items():
                    expanded = re.sub(
                        rf"\\{re.escape(macro)}(?![A-Za-z@])",
                        str(replacement),
                        expanded,
                    )
                cleaned = _clean_tikz_label(expanded)
                if cleaned and not re.search(r"\\[A-Za-z@]+", cleaned):
                    _append_unique(labels, cleaned)
    for label in static_labels:
        _append_unique(labels, label)
    return labels


def build_figure_concepts(
    element: Element,
    nearby_text: list[str],
    visible_labels: list[str] | None = None,
    hidden_labels: list[str] | None = None,
) -> ConceptSet:
    # Build required and excluded concepts for one figure
    hidden = _unique_clean(hidden_labels or [])
    if element.subtype != "diagram":
        issue = Issue(
            element_id=element.id,
            code="coverage_unavailable",
            severity="info",
            message="Concept coverage is unavailable for a raster figure",
        )
        return ConceptSet(
            required=[],
            excluded=[],
            visible_labels=[],
            hidden_labels=[],
            issues=[issue],
        )
    labels = visible_labels
    if labels is None:
        raw = _figure_source(element)
        parsed = element.attrs.get("tikz_labels")
        parsed_labels: list[str] = []
        if isinstance(parsed, list):
            for value in parsed:
                if isinstance(value, str):
                    parsed_labels.append(value)
        labels = infer_tikz_labels(raw, parsed_labels)
    visible = _unique_clean(labels)
    hidden_normalized: set[str] = set()
    for label in hidden:
        hidden_normalized.add(normalize_text(label))
    filtered_visible: list[str] = []
    for label in visible:
        if normalize_text(label) not in hidden_normalized:
            filtered_visible.append(label)
    required = _label_concepts_with_sequences(filtered_visible)
    excluded: list[str] = []
    for label in hidden:
        excluded.append(f"label:{label}")
    retained: list[str] = []
    combined_nearby = normalize_text(" ".join(nearby_text))
    for concept in required:
        if _concept_matches_normalized(combined_nearby, concept):
            excluded.append(concept)
        else:
            retained.append(concept)
    return ConceptSet(
        required=retained,
        excluded=excluded,
        visible_labels=filtered_visible,
        hidden_labels=hidden,
    )


def apply_concepts(element: Element, concepts: ConceptSet) -> Element:
    # Return an element carrying the computed concepts
    updated = element.model_copy(deep=True)
    updated.fidelity.required_concepts = list(concepts.required)
    updated.fidelity.excluded_concepts = list(concepts.excluded)
    return updated


def evaluate_coverage(alt_text: str | None, required_concepts: list[str]) -> CoverageResult:
    # Measure deterministic concept coverage
    if not required_concepts:
        return CoverageResult(coverage=None, matched=[], missing=[], applicable=False)
    normalized = normalize_text(alt_text or "")
    matched: list[str] = []
    missing: list[str] = []
    for concept in required_concepts:
        if _concept_matches_normalized(normalized, concept):
            matched.append(concept)
        else:
            missing.append(concept)
    return CoverageResult(
        coverage=len(matched) / len(required_concepts),
        matched=matched,
        missing=missing,
        applicable=True,
    )


def concept_matches(text: str, concept: str) -> bool:
    # Match one grammar concept against text
    return _concept_matches_normalized(normalize_text(text), concept)


def _figure_source(element: Element) -> str:
    # Read embedded figure source without assuming its adapter
    source = element.content.get("source")
    if isinstance(source, dict):
        raw = source.get("raw")
        if isinstance(raw, str):
            return raw
    return element.source.raw or ""


def _label_concepts_with_sequences(labels: list[str]) -> list[str]:
    # Replace numbered label runs with sequence concepts
    groups: dict[str, list[tuple[str, int]]] = {}
    stems: dict[str, str] = {}
    for label in labels:
        match = re.fullmatch(r"(.+?)\s*(\d+)", label.strip())
        if match is None:
            continue
        stem = match.group(1).strip()
        key = normalize_text(stem)
        values = groups.setdefault(key, [])
        values.append((label, int(match.group(2))))
        stems.setdefault(key, stem)
    sequences: dict[str, tuple[int, set[str]]] = {}
    for key, values in groups.items():
        numbers: set[int] = set()
        member_labels: set[str] = set()
        for label, number in values:
            numbers.add(number)
            member_labels.add(normalize_text(label))
        if len(numbers) < 3:
            continue
        minimum = min(numbers)
        maximum = max(numbers)
        sequence_count = maximum
        if minimum == 0:
            sequence_count = maximum + 1
        expected_span = maximum - minimum + 1
        if expected_span - len(numbers) > 1:
            continue
        sequences[key] = (sequence_count, member_labels)
    concepts: list[str] = []
    emitted: set[str] = set()
    for label in labels:
        normalized_label = normalize_text(label)
        sequence_key = None
        for key, sequence_data in sequences.items():
            if normalized_label in sequence_data[1]:
                sequence_key = key
                break
        if sequence_key is None:
            concepts.append(f"label:{label}")
            continue
        if sequence_key in emitted:
            continue
        count = sequences[sequence_key][0]
        concepts.append(f"sequence:{count}:{stems[sequence_key]}")
        emitted.add(sequence_key)
    return concepts


def _concept_matches_normalized(normalized_text: str, concept: str) -> bool:
    # Apply the concept grammar to normalized text
    if concept.startswith("label:"):
        label = normalize_text(concept[6:])
        return _contains_phrase(normalized_text, label)
    parts = concept.split(":", 2)
    if len(parts) != 3 or parts[0] not in {"sequence", "count"}:
        return False
    try:
        count = int(parts[1])
    except ValueError:
        return False
    noun = normalize_text(parts[2])
    return _contains_count(normalized_text, count) and _contains_stem(normalized_text, noun)


def _contains_phrase(normalized_text: str, phrase: str) -> bool:
    # Match a normalized phrase at word boundaries
    if not phrase:
        return False
    pattern = rf"(?<![\w-]){re.escape(phrase)}(?![\w-])"
    return re.search(pattern, normalized_text) is not None


def _contains_count(normalized_text: str, count: int) -> bool:
    # Match a digit or supported number word
    if _contains_phrase(normalized_text, str(count)):
        return True
    word = NUMBER_WORDS.get(count)
    if word is None:
        return False
    return _contains_phrase(normalized_text, word)


def _contains_stem(normalized_text: str, stem: str) -> bool:
    # Match singular and simple plural stems
    if _contains_phrase(normalized_text, stem):
        return True
    if stem.endswith("s"):
        singular = stem[:-1]
        return bool(singular) and _contains_phrase(normalized_text, singular)
    plural = stem + "s"
    if re.search(r"(?:s|x|z|ch|sh)$", stem):
        plural = stem + "es"
    elif stem.endswith("y") and len(stem) > 1 and stem[-2] not in "aeiou":
        plural = stem[:-1] + "ies"
    return _contains_phrase(normalized_text, plural)


def _unique_clean(values: list[str]) -> list[str]:
    # Preserve unique nonempty labels in order
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = re.sub(r"\s+", " ", value).strip()
        key = normalize_text(cleaned)
        if cleaned and key not in seen:
            result.append(cleaned)
            seen.add(key)
    return result


def _append_unique(values: list[str], value: str) -> None:
    # Append a label once using normalized equality
    normalized = normalize_text(value)
    for existing in values:
        if normalize_text(existing) == normalized:
            return
    values.append(value)


def _clean_tikz_label(value: str) -> str:
    # Remove presentational TeX from a node label
    cleaned = re.sub(
        r"\\(?:tiny|scriptsize|footnotesize|small|normalsize|large|Large|LARGE|huge|Huge)\b",
        " ",
        value,
    )
    cleaned = cleaned.replace("{", " ").replace("}", " ")
    cleaned = cleaned.replace(r"\ ", " ")
    return re.sub(r"\s+", " ", cleaned).strip()


def _foreach_blocks(source: str) -> list[tuple[str, list[int], str]]:
    # Extract balanced supported TikZ foreach bodies
    blocks: list[tuple[str, list[int], str]] = []
    pattern = re.compile(r"\\foreach\s+\\([A-Za-z@]+)\s+in\s*\{([^{}]+)\}\s*\{")
    position = 0
    while True:
        match = pattern.search(source, position)
        if match is None:
            break
        body_start = match.end()
        body_end = _balanced_group_end(source, body_start - 1)
        if body_end is None:
            break
        values = _foreach_values(match.group(2))
        if values:
            blocks.append((match.group(1), values, source[body_start:body_end]))
        position = body_end + 1
    return blocks


def _balanced_group_end(text: str, opening: int) -> int | None:
    # Find the closing brace for one group
    depth = 0
    escaped = False
    for index in range(opening, len(text)):
        character = text[index]
        if escaped:
            escaped = False
            continue
        if character == "\\":
            escaped = True
            continue
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return index
    return None


def _foreach_values(specification: str) -> list[int]:
    # Parse integer lists and inclusive ranges
    values: list[int] = []
    range_match = re.fullmatch(r"\s*(-?\d+)\s*,\s*\.\.\.\s*,\s*(-?\d+)\s*", specification)
    if range_match is not None:
        start = int(range_match.group(1))
        end = int(range_match.group(2))
        step = 1
        if end < start:
            step = -1
        current = start
        while True:
            values.append(current)
            if current == end:
                break
            current += step
        return values
    for part in specification.split(","):
        stripped = part.strip()
        if re.fullmatch(r"-?\d+", stripped) is None:
            return []
        values.append(int(stripped))
    return values


def _foreach_assignments(body: str, variable: str) -> dict[str, str]:
    # Read integer macro assignments in a foreach body
    assignments: dict[str, str] = {}
    pattern = re.compile(r"\\pgfmathtruncatemacro\s*\{\\([A-Za-z@]+)\}\s*\{([^{}]+)\}")
    for match in pattern.finditer(body):
        if re.search(rf"\\{re.escape(variable)}(?![A-Za-z@])", match.group(2)):
            assignments[match.group(1)] = match.group(2)
    return assignments


def _evaluate_foreach_expression(expression: str, variable: str, value: int) -> int | None:
    # Evaluate one simple integer foreach expression
    normalized = re.sub(r"\s+", "", expression)
    match = re.fullmatch(
        rf"\\{re.escape(variable)}(?:([+\-*/])(-?\d+))?",
        normalized,
    )
    if match is None:
        return None
    operator = match.group(1)
    if operator is None:
        return value
    operand = int(match.group(2))
    if operator == "+":
        return value + operand
    if operator == "-":
        return value - operand
    if operator == "*":
        return value * operand
    if operand == 0:
        return None
    return int(value / operand)


def _node_label_templates(body: str) -> list[str]:
    # Extract simple node label templates
    templates: list[str] = []
    pattern = re.compile(r"\\node\b[^;{}]*\{([^{}]*)\}\s*;")
    for match in pattern.finditer(body):
        templates.append(match.group(1))
    return templates

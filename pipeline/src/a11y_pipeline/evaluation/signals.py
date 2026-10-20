import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from a11y_pipeline.evaluation.concepts import normalize_text
from a11y_pipeline.ir.models import Issue

# Alt text may use this many words plus this many more for each required label
ALT_BASE_WORD_LIMIT = 40
ALT_WORDS_PER_CONCEPT = 40
FORBIDDEN_OPENERS = ("image of", "picture of", "graphic of")
FILE_NAME_PATTERN = re.compile(
    r"(?:[A-Za-z]:)?(?:[^/\s\\]+[/\\])*[^/\s\\]+\."
    r"(?:bmp|eps|gif|jpe?g|pdf|png|svg|tiff?|webp)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SignalResult:
    flags: list[str]
    issues: list[Issue]
    word_count: int
    length_limit: int

    @property
    def warning_count(self) -> int:
        # Count warning signal issues
        count = 0
        for issue in self.issues:
            if issue.severity == "warning":
                count += 1
        return count


def evaluate_signals(
    element_id: str,
    alt_text: str | None,
    required_concepts: list[str],
    nearby_text: list[str],
) -> SignalResult:
    # Evaluate deterministic alt text quality signals
    text = (alt_text or "").strip()
    words = re.findall(r"\b[\w'-]+\b", text)
    length_limit = ALT_WORDS_PER_CONCEPT * len(required_concepts) + ALT_BASE_WORD_LIMIT
    flags: list[str] = []
    issues: list[Issue] = []
    if not text:
        _add_flag(
            flags,
            issues,
            element_id,
            "alt_missing",
            "error",
            "Figure alternative text is missing",
        )
        return SignalResult(
            flags=flags,
            issues=issues,
            word_count=0,
            length_limit=length_limit,
        )
    if FILE_NAME_PATTERN.fullmatch(text) is not None:
        _add_flag(
            flags,
            issues,
            element_id,
            "alt_file_name",
            "warning",
            "Figure alternative text is only a file name or path",
        )
    normalized = normalize_text(text)
    for opener in FORBIDDEN_OPENERS:
        if normalized.startswith(opener):
            _add_flag(
                flags,
                issues,
                element_id,
                "alt_forbidden_opener",
                "warning",
                "Figure alternative text starts with a forbidden generic opener",
            )
            break
    duplicate_ratio = _maximum_similarity(normalized, nearby_text)
    if duplicate_ratio >= 0.9:
        _add_flag(
            flags,
            issues,
            element_id,
            "alt_near_duplicate",
            "warning",
            "Figure alternative text repeats nearby text",
            {"similarity": duplicate_ratio},
        )
    if len(words) > length_limit:
        _add_flag(
            flags,
            issues,
            element_id,
            "alt_length_outlier",
            "warning",
            "Figure alternative text is a length outlier",
            {"word_count": len(words), "limit": length_limit},
        )
    return SignalResult(
        flags=flags,
        issues=issues,
        word_count=len(words),
        length_limit=length_limit,
    )


def _maximum_similarity(alt_text: str, nearby_text: list[str]) -> float:
    # Find the strongest normalized nearby text similarity
    maximum = 0.0
    for nearby in nearby_text:
        normalized = normalize_text(nearby)
        if not normalized:
            continue
        ratio = SequenceMatcher(None, alt_text, normalized).ratio()
        if ratio > maximum:
            maximum = ratio
    return maximum


def _add_flag(
    flags: list[str],
    issues: list[Issue],
    element_id: str,
    code: str,
    severity: str,
    message: str,
    details: dict[str, object] | None = None,
) -> None:
    # Add one signal and its canonical issue
    flags.append(code)
    issue_details: dict[str, object] = {}
    if details is not None:
        issue_details.update(details)
    issues.append(
        Issue(
            element_id=element_id,
            code=code,
            severity=severity,
            message=message,
            details=issue_details,
        )
    )

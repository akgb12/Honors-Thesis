from dataclasses import dataclass

ACCESSIBILITY_WEIGHTS = {
    "T": 0.18,
    "R": 0.15,
    "H": 0.10,
    "I": 0.15,
    "B": 0.10,
    "M": 0.10,
    "D": 0.07,
    "C": 0.15,
}

FIDELITY_WEIGHTS = {
    "X": 0.25,
    "E": 0.15,
    "G": 0.15,
    "B_f": 0.15,
    "S": 0.10,
    "Q_s": 0.15,
    "O": 0.05,
}


@dataclass(frozen=True)
class IndexScore:
    name: str
    value: float | None
    applicable_metrics: dict[str, float]
    excluded_metrics: list[str]
    preliminary: bool = True


@dataclass(frozen=True)
class ScoreReport:
    accessibility: IndexScore
    fidelity: IndexScore

    def candidate_scores(self) -> dict[str, float]:
        # Flatten only separate A and F candidate indices
        scores: dict[str, float] = {}
        if self.accessibility.value is not None:
            scores["A"] = self.accessibility.value
        if self.fidelity.value is not None:
            scores["F"] = self.fidelity.value
        return scores


def score_accessibility(metrics: dict[str, float | None]) -> IndexScore:
    # Compute preliminary A with applicable metric renormalization
    return _weighted_index("A", metrics, ACCESSIBILITY_WEIGHTS)


def score_fidelity(metrics: dict[str, float | None]) -> IndexScore:
    # Compute preliminary F with applicable metric renormalization
    return _weighted_index("F", metrics, FIDELITY_WEIGHTS)


def compute_preliminary_scores(
    accessibility_metrics: dict[str, float | None],
    fidelity_metrics: dict[str, float | None],
) -> ScoreReport:
    # Compute separate preliminary accessibility and fidelity indices
    return ScoreReport(
        accessibility=score_accessibility(accessibility_metrics),
        fidelity=score_fidelity(fidelity_metrics),
    )


def figure_accessibility_score(
    alt_present: bool,
    coverage: float | None,
    warning_count: int,
    vetoed: bool = False,
    missing_asset: bool = False,
) -> float:
    # Score one figure using the provisional Mark 1 definition
    if vetoed or missing_asset or not alt_present:
        return 0.0
    if warning_count < 0:
        raise ValueError("Warning count must not be negative")
    if coverage is None:
        if warning_count == 0:
            return 60.0
        return 0.0
    if coverage < 0.0 or coverage > 1.0:
        raise ValueError("Coverage must be between zero and one")
    return max(0.0, coverage * 100.0 - warning_count * 20.0)


def _weighted_index(
    name: str,
    metrics: dict[str, float | None],
    weights: dict[str, float],
) -> IndexScore:
    # Renormalize one index over applicable known metrics
    applicable: dict[str, float] = {}
    excluded: list[str] = []
    weighted_sum = 0.0
    weight_sum = 0.0
    for metric, weight in weights.items():
        value = metrics.get(metric)
        if value is None:
            excluded.append(metric)
            continue
        numeric = float(value)
        if numeric < 0.0 or numeric > 100.0:
            raise ValueError(f"Metric {metric} must be between zero and one hundred")
        applicable[metric] = numeric
        weighted_sum += weight * numeric
        weight_sum += weight
    value = None
    if weight_sum > 0.0:
        value = weighted_sum / weight_sum
    return IndexScore(
        name=name,
        value=value,
        applicable_metrics=applicable,
        excluded_metrics=excluded,
    )

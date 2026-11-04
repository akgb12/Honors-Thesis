from a11y_pipeline.ir.models import Candidate


def candidate_passes_floors(
    candidate: Candidate,
    floor_a: float,
    floor_f: float,
) -> bool:
    # Check vetoes and both score floors
    if candidate.vetoes:
        return False
    score_a = candidate.scores.get("A")
    score_f = candidate.scores.get("F")
    if score_a is None or score_f is None:
        return False
    return score_a >= floor_a and score_f >= floor_f


def select_best_candidate(
    candidates: list[Candidate],
    floor_a: float,
    floor_f: float,
) -> Candidate:
    # Select the highest qualified accessibility candidate
    if not candidates:
        raise ValueError("at least one candidate is required")
    qualified: list[Candidate] = []
    fallback: Candidate | None = None
    for candidate in candidates:
        if candidate.candidate_id == "c0":
            fallback = candidate
        if candidate_passes_floors(candidate, floor_a, floor_f):
            qualified.append(candidate)
    if qualified:
        best = qualified[0]
        for candidate in qualified[1:]:
            best_key = (best.scores["A"], best.scores["F"])
            candidate_key = (candidate.scores["A"], candidate.scores["F"])
            if candidate_key > best_key:
                best = candidate
        return best
    if fallback is not None:
        return fallback
    raise ValueError("no candidate passes selection floors and c0 is unavailable")


def accepts_candidate(previous: Candidate, current: Candidate) -> bool:
    # Accept a nonveto candidate that does not regress
    if current.vetoes:
        return False
    previous_a = previous.scores.get("A", 0.0)
    previous_f = previous.scores.get("F", 0.0)
    current_a = current.scores.get("A", 0.0)
    current_f = current.scores.get("F", 0.0)
    return (current_a, current_f) >= (previous_a, previous_f)

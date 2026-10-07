import pytest

from a11y_pipeline.config import Settings
from a11y_pipeline.ir.models import Candidate, Issue
from a11y_pipeline.orchestration.effort import (
    ELEMENT_REPAIR_LIMIT,
    dollar_cap,
    round_cap,
)
from a11y_pipeline.orchestration.selection import select_best_candidate
from a11y_pipeline.orchestration.stopping import StopContext, decide_stop


def _candidate(
    candidate_id: str,
    score_a: float,
    score_f: float,
    vetoed: bool = False,
) -> Candidate:
    # Build one selection candidate
    vetoes: list[Issue] = []
    if vetoed:
        vetoes.append(
            Issue(
                element_id=None,
                code="visual_change",
                severity="veto",
                message="The page changed",
            )
        )
    return Candidate(
        candidate_id=candidate_id,
        round=0,
        patches=[],
        scores={"A": score_a, "F": score_f},
        vetoes=vetoes,
    )


def _stop_context(**updates: object) -> StopContext:
    # Build a default active stop context
    values: dict[str, object] = {
        "failing_element_ids": ["figure"],
        "current_round": 0,
        "round_cap": 3,
        "budget_spent": 0.0,
        "dollar_cap": 1.5,
        "accepted_improvement": True,
        "repair_counts": {"figure": 0},
        "repair_limit": 2,
        "budget_exhausted": False,
    }
    values.update(updates)
    return StopContext(**values)


def test_effort_caps_are_exact() -> None:
    # Keep effort limits fixed to the Mark 1 contract
    settings = Settings(_env_file=None)

    assert round_cap("baseline") == 0
    assert round_cap("low") == 1
    assert round_cap("medium") == 3
    assert round_cap("high") == 5
    assert ELEMENT_REPAIR_LIMIT == 2
    assert dollar_cap("baseline", settings) == 0.50
    assert dollar_cap("low", settings) == 0.50
    assert dollar_cap("medium", settings) == 1.50
    assert dollar_cap("high", settings) == 3.00


@pytest.mark.parametrize(
    ("updates", "expected"),
    [
        ({"failing_element_ids": []}, "nothing_failing"),
        ({"current_round": 3}, "round_cap"),
        ({"repair_counts": {"figure": 2}}, "round_cap"),
        ({"budget_spent": 1.5}, "budget_cap"),
        ({"budget_exhausted": True}, "budget_cap"),
        (
            {"current_round": 1, "accepted_improvement": False},
            "no_accepted_improvement",
        ),
    ],
)
def test_all_stop_rules(updates: dict[str, object], expected: str) -> None:
    # Return the first matching stop reason
    assert decide_stop(_stop_context(**updates)) == expected


def test_stop_rules_continue_when_limits_allow() -> None:
    # Continue while failures remain repairable
    assert decide_stop(_stop_context()) is None


def test_candidate_selection_filters_vetoes_and_floors() -> None:
    # Select by accessibility then fidelity after filtering
    candidates = [
        _candidate("c0", 0, 100),
        _candidate("c1", 80, 95),
        _candidate("c2", 90, 89),
        _candidate("c3", 90, 95, vetoed=True),
        _candidate("c4", 80, 98),
        _candidate("c5", 85, 91),
    ]

    selected = select_best_candidate(candidates, floor_a=60, floor_f=90)

    assert selected.candidate_id == "c5"


def test_candidate_selection_uses_fidelity_tie_break() -> None:
    # Break equal accessibility scores with fidelity
    candidates = [
        _candidate("c0", 0, 100),
        _candidate("c1", 80, 95),
        _candidate("c2", 80, 98),
    ]

    selected = select_best_candidate(candidates, floor_a=60, floor_f=90)

    assert selected.candidate_id == "c2"


def test_candidate_selection_falls_back_to_c0() -> None:
    # Preserve deterministic fallback when floors fail
    candidates = [
        _candidate("c0", 0, 100),
        _candidate("c1", 59, 100),
    ]

    selected = select_best_candidate(candidates, floor_a=60, floor_f=90)

    assert selected.candidate_id == "c0"

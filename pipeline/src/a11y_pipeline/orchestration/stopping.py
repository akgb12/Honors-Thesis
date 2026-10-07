from dataclasses import dataclass
from typing import Literal

StopReason = Literal[
    "nothing_failing",
    "round_cap",
    "budget_cap",
    "no_accepted_improvement",
]


@dataclass(frozen=True)
class StopContext:
    failing_element_ids: list[str]
    current_round: int
    round_cap: int
    budget_spent: float
    dollar_cap: float
    accepted_improvement: bool
    repair_counts: dict[str, int]
    repair_limit: int
    budget_exhausted: bool = False


def decide_stop(context: StopContext) -> StopReason | None:
    # Apply the four stop rules in order
    if not context.failing_element_ids:
        return "nothing_failing"
    repairable = False
    for element_id in context.failing_element_ids:
        if context.repair_counts.get(element_id, 0) < context.repair_limit:
            repairable = True
            break
    if context.current_round >= context.round_cap or not repairable:
        return "round_cap"
    if context.budget_exhausted or context.budget_spent >= context.dollar_cap:
        return "budget_cap"
    if context.current_round > 0 and not context.accepted_improvement:
        return "no_accepted_improvement"
    return None

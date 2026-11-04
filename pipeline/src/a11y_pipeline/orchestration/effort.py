from typing import Literal

from a11y_pipeline.config import Settings

Effort = Literal["baseline", "low", "medium", "high"]

ROUND_CAPS: dict[Effort, int] = {
    "baseline": 0,
    "low": 1,
    "medium": 3,
    "high": 5,
}
ELEMENT_REPAIR_LIMIT = 2


def round_cap(effort: Effort) -> int:
    # Return the exact repair round cap
    return ROUND_CAPS[effort]


def dollar_cap(effort: Effort, settings: Settings) -> float:
    # Return the configured run dollar cap
    if effort == "high":
        return settings.run_dollar_cap_high
    if effort == "medium":
        return settings.run_dollar_cap_medium
    return settings.run_dollar_cap_low

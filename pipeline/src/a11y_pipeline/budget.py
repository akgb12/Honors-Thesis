import json
import math
from dataclasses import dataclass

from a11y_pipeline.models.client import ModelClient, ModelRequest, ModelResponse
from a11y_pipeline.models.pricing import ModelPricing


class BudgetExceeded(RuntimeError):
    pass


def estimate_input_tokens(request: ModelRequest) -> int:
    # Estimate text schema and image tokens conservatively
    characters = len(request.system)
    characters += len(json.dumps(request.output_schema.model_json_schema(), sort_keys=True))
    image_tokens = 0
    for message in request.messages:
        characters += len(message.role)
        characters += len(message.text)
        if message.image_png is not None:
            image_tokens += math.ceil(len(message.image_png) / 750)
    return max(1, math.ceil(characters / 4) + image_tokens)


@dataclass
class Budget:
    cap_usd: float
    spent_usd: float = 0.0

    def estimate(self, request: ModelRequest, pricing: ModelPricing) -> float:
        # Estimate the highest cost of the next call
        input_tokens = estimate_input_tokens(request)
        return pricing.cost(input_tokens, request.max_tokens)

    def check(self, request: ModelRequest, pricing: ModelPricing) -> float:
        # Refuse calls whose estimate would exceed the cap
        estimated_cost = self.estimate(request, pricing)
        if self.spent_usd + estimated_cost > self.cap_usd:
            raise BudgetExceeded(
                f"model call estimate ${estimated_cost:.6f} would exceed "
                f"remaining budget ${max(0.0, self.cap_usd - self.spent_usd):.6f}"
            )
        return estimated_cost

    def record(self, actual_cost_usd: float) -> None:
        # Accumulate actual model cost after a call
        if actual_cost_usd < 0:
            raise ValueError("actual model cost cannot be negative")
        self.spent_usd += actual_cost_usd


class BudgetedModelClient:
    def __init__(
        self,
        client: ModelClient,
        budget: Budget,
        pricing: ModelPricing,
    ) -> None:
        # Store the model client and cost controls
        self.client = client
        self.budget = budget
        self.pricing = pricing

    def complete_structured(self, request: ModelRequest) -> ModelResponse:
        # Check the estimate and record the actual call cost
        estimated_cost = self.budget.check(request, self.pricing)
        try:
            response = self.client.complete_structured(request)
        except Exception:
            self.budget.record(estimated_cost)
            raise
        self.budget.record(response.cost_usd)
        return response

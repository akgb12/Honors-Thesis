from dataclasses import dataclass

from a11y_pipeline.config import Settings


@dataclass(frozen=True)
class ModelPricing:
    input_usd_per_mtok: float
    output_usd_per_mtok: float

    @classmethod
    def from_settings(cls, settings: Settings) -> "ModelPricing":
        # Build pricing from validated model settings
        if settings.model_input_usd_per_mtok is None:
            raise ValueError("MODEL_INPUT_USD_PER_MTOK is required for model pricing")
        if settings.model_output_usd_per_mtok is None:
            raise ValueError("MODEL_OUTPUT_USD_PER_MTOK is required for model pricing")
        return cls(
            input_usd_per_mtok=settings.model_input_usd_per_mtok,
            output_usd_per_mtok=settings.model_output_usd_per_mtok,
        )

    def cost(self, input_tokens: int, output_tokens: int) -> float:
        # Calculate model cost from token counts
        input_cost = input_tokens * self.input_usd_per_mtok / 1_000_000
        output_cost = output_tokens * self.output_usd_per_mtok / 1_000_000
        return input_cost + output_cost

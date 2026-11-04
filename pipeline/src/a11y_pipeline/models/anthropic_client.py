import base64
import json
from time import perf_counter
from typing import Any

from anthropic import Anthropic, transform_schema

from a11y_pipeline.config import Settings
from a11y_pipeline.models.client import ModelRequest, ModelResponse
from a11y_pipeline.models.pricing import ModelPricing

# Models whose default adaptive thinking would use the small output budget; thinking is
# switched off between tool calls for these extraction requests
NO_THINKING_MODELS = ("claude-sonnet-5-5",)


class MissingStructuredOutput(ValueError):
    def __init__(
        self,
        message: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        # Keep billed usage so failed calls still appear in telemetry
        super().__init__(message)
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cost_usd = cost_usd


class AnthropicModelClient:
    def __init__(self, settings: Settings) -> None:
        # Build a guarded Anthropic SDK client from validated settings
        if settings.anthropic_api_key is None:
            raise ValueError("ANTHROPIC_API_KEY is required to construct the Anthropic client")
        api_key = settings.anthropic_api_key.get_secret_value()
        if not api_key.strip():
            raise ValueError("ANTHROPIC_API_KEY is required to construct the Anthropic client")
        self.pricing = ModelPricing.from_settings(settings)
        self.model = settings.generator_model
        self._client = Anthropic(api_key=api_key, max_retries=0)

    def complete_structured(self, request: ModelRequest) -> ModelResponse:
        # Request schema constrained JSON and validate it
        messages = self._build_messages(request)
        options: dict[str, Any] = {}
        if self.model in NO_THINKING_MODELS:
            options["thinking"] = {"type": "between_tools"}
        started = perf_counter()
        response = self._client.messages.create(
            model=self.model,
            system=request.system,
            messages=messages,
            max_tokens=request.max_tokens,
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": transform_schema(request.output_schema),
                }
            },
            **options,
        )
        latency_ms = (perf_counter() - started) * 1000
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        cost_usd = self.pricing.cost(input_tokens, output_tokens)
        try:
            payload = self._structured_payload(response.content, response.stop_reason)
            parsed = request.output_schema.model_validate(payload)
        except MissingStructuredOutput as error:
            raise MissingStructuredOutput(
                str(error), input_tokens, output_tokens, cost_usd
            ) from error
        except ValueError as error:
            raise MissingStructuredOutput(
                f"Anthropic response did not match the output schema: {error}",
                input_tokens,
                output_tokens,
                cost_usd,
            ) from error
        return ModelResponse(
            output=parsed,
            raw_text=json.dumps(payload, sort_keys=True, separators=(",", ":")),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            cost_usd=cost_usd,
            cached=False,
        )

    def _build_messages(self, request: ModelRequest) -> list[dict[str, Any]]:
        # Convert text and PNG values into Anthropic content blocks
        messages: list[dict[str, Any]] = []
        for message in request.messages:
            content: list[dict[str, Any]] = []
            if message.text:
                content.append({"type": "text", "text": message.text})
            if message.image_png is not None:
                encoded = base64.b64encode(message.image_png).decode("ascii")
                content.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": encoded,
                        },
                    }
                )
            messages.append({"role": message.role, "content": content})
        return messages

    def _structured_payload(self, content: list[Any], stop_reason: str | None) -> Any:
        # Decode the JSON text block, naming the stop reason when it is missing or cut off
        text = "".join(
            getattr(block, "text", "")
            for block in content
            if getattr(block, "type", None) == "text"
        ).strip()
        try:
            return json.loads(text)
        except ValueError as error:
            raise MissingStructuredOutput(
                f"Anthropic response was not valid JSON (stop reason: {stop_reason})"
            ) from error

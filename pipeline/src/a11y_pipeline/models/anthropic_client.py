import base64
import json
from time import perf_counter
from typing import Any

from anthropic import Anthropic

from a11y_pipeline.config import Settings
from a11y_pipeline.models.client import ModelRequest, ModelResponse
from a11y_pipeline.models.pricing import ModelPricing

# Newer models reject forced tool choice, so the prompt names the tool instead
SUBMIT_INSTRUCTION = "Respond by calling the submit tool exactly once with your answer."

# Models whose default adaptive thinking would use the small output budget; thinking is
# switched off between tool calls for these extraction requests
NO_THINKING_MODELS = ("claude-sonnet-5-5",)


class MissingToolOutput(ValueError):
    pass


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
        # Ask for one submit tool call and validate its input
        messages = self._build_messages(request)
        tool = {
            "name": "submit",
            "description": "Submit the structured response",
            "input_schema": request.output_schema.model_json_schema(),
        }
        started = perf_counter()
        options: dict[str, Any] = {}
        if self.model in NO_THINKING_MODELS:
            options["thinking"] = {"type": "between_tools"}
        response = self._client.messages.create(
            model=self.model,
            system=f"{request.system}\n\n{SUBMIT_INSTRUCTION}",
            messages=messages,
            max_tokens=request.max_tokens,
            tools=[tool],
            tool_choice={"type": "auto"},
            **options,
        )
        latency_ms = (perf_counter() - started) * 1000
        tool_input = self._submit_tool_input(response.content, response.stop_reason)
        parsed = request.output_schema.model_validate(tool_input)
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        return ModelResponse(
            output=parsed,
            raw_text=json.dumps(tool_input, sort_keys=True, separators=(",", ":")),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            cost_usd=self.pricing.cost(input_tokens, output_tokens),
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

    def _submit_tool_input(self, content: list[Any], stop_reason: str | None) -> Any:
        # Find the submit tool result
        for block in content:
            if getattr(block, "type", None) != "tool_use":
                continue
            if getattr(block, "name", None) != "submit":
                continue
            return block.input
        raise MissingToolOutput(
            "Anthropic response did not contain the submit tool output "
            f"(stop reason: {stop_reason})"
        )

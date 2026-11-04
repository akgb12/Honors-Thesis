import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from time import perf_counter

from pydantic import BaseModel

from a11y_pipeline.models.client import ModelRequest, ModelResponse, ScriptValue


@dataclass(frozen=True)
class FakeScriptResponse:
    output: ScriptValue
    input_tokens: int = 12
    output_tokens: int = 8
    raw_text: str | None = None


FakeGenerator = Callable[[ModelRequest], ScriptValue | FakeScriptResponse]


class FakeModelClient:
    def __init__(
        self,
        scripts: Mapping[str, Sequence[ScriptValue | FakeScriptResponse]] | None = None,
        default_generator: FakeGenerator | None = None,
    ) -> None:
        # Copy scripts so caller data is never mutated
        self._scripts: dict[str, list[ScriptValue | FakeScriptResponse]] = {}
        if scripts is not None:
            for element_id, values in scripts.items():
                self._scripts[element_id] = list(values)
        self._positions: dict[str, int] = {}
        self._default_generator = default_generator
        self.requests: list[ModelRequest] = []

    @classmethod
    def weak_then_good(
        cls,
        element_id: str,
        weak: ScriptValue,
        good: ScriptValue,
    ) -> "FakeModelClient":
        # Create the standard repair demonstration script
        scripts = {element_id: [weak, good]}
        return cls(scripts=scripts)

    def complete_structured(self, request: ModelRequest) -> ModelResponse:
        # Return the next deterministic scripted output
        started = perf_counter()
        self.requests.append(request)
        scripted = self._next_value(request)
        fake_response = self._as_script_response(scripted)
        if isinstance(fake_response.output, BaseModel):
            payload = fake_response.output.model_dump(mode="json")
        else:
            payload = fake_response.output
        raw_text = fake_response.raw_text
        if raw_text is None:
            raw_text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        parsed = request.output_schema.model_validate(payload)
        latency_ms = (perf_counter() - started) * 1000
        return ModelResponse(
            output=parsed,
            raw_text=raw_text,
            input_tokens=fake_response.input_tokens,
            output_tokens=fake_response.output_tokens,
            latency_ms=latency_ms,
            cost_usd=0.0,
            cached=False,
        )

    def _next_value(
        self,
        request: ModelRequest,
    ) -> ScriptValue | FakeScriptResponse:
        # Select a script item or invoke the fallback generator
        values = self._scripts.get(request.element_id)
        position = self._positions.get(request.element_id, 0)
        if values is not None and position < len(values):
            self._positions[request.element_id] = position + 1
            return values[position]
        if self._default_generator is not None:
            return self._default_generator(request)
        raise LookupError(f"no fake model response for element {request.element_id}")

    def _as_script_response(
        self,
        value: ScriptValue | FakeScriptResponse,
    ) -> FakeScriptResponse:
        # Normalize one script item
        if isinstance(value, FakeScriptResponse):
            return value
        return FakeScriptResponse(output=value)

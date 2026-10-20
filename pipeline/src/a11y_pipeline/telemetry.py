import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from a11y_pipeline.models.client import ModelClient, ModelRequest, ModelResponse

REDACTED = "[REDACTED]"
_SECRET_MARKERS = ("KEY", "SECRET", "TOKEN", "PASSWORD")
_SAFE_TOKEN_FIELDS = {"input_tokens", "output_tokens", "max_tokens"}


def _is_secret_field(name: str) -> bool:
    # Detect credential shaped field names
    normalized = name.lower()
    if normalized in _SAFE_TOKEN_FIELDS:
        return False
    upper_name = name.upper()
    for marker in _SECRET_MARKERS:
        if marker in upper_name:
            return True
    return False


def redact_secret_fields(value: Any) -> Any:
    # Redact credentials recursively for telemetry and manifests
    if isinstance(value, Mapping):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if _is_secret_field(key_text):
                redacted[key_text] = REDACTED
            else:
                redacted[key_text] = redact_secret_fields(item)
        return redacted
    if isinstance(value, (list, tuple)):
        redacted_items: list[Any] = []
        for item in value:
            redacted_items.append(redact_secret_fields(item))
        return redacted_items
    return value


class TelemetryWriter:
    def __init__(self, path: Path) -> None:
        # Store the append only telemetry path
        self.path = path

    def append(self, event: Mapping[str, Any]) -> None:
        # Append one redacted stable JSON line
        self.path.parent.mkdir(parents=True, exist_ok=True)
        safe_event = redact_secret_fields(event)
        line = json.dumps(safe_event, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        with self.path.open("a", encoding="utf-8") as telemetry_file:
            telemetry_file.write(line)
            telemetry_file.write("\n")


class TelemetryModelClient:
    def __init__(self, client: ModelClient, writer: TelemetryWriter) -> None:
        # Store the wrapped client and telemetry writer
        self.client = client
        self.writer = writer

    def complete_structured(self, request: ModelRequest) -> ModelResponse:
        # Record exactly one safe event for each attempted call
        event: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "model": request.model,
            "prompt_version": request.prompt_version,
            "element_id": request.element_id,
            "max_tokens": request.max_tokens,
        }
        try:
            response = self.client.complete_structured(request)
        except Exception as error:
            event["status"] = "error"
            event["error_type"] = type(error).__name__
            for name in ("input_tokens", "output_tokens"):
                value = getattr(error, name, None)
                if isinstance(value, int):
                    event[name] = value
            cost = getattr(error, "cost_usd", None)
            if isinstance(cost, float):
                event["cost_usd"] = cost
            self.writer.append(event)
            raise
        event["status"] = "ok"
        event["input_tokens"] = response.input_tokens
        event["output_tokens"] = response.output_tokens
        event["latency_ms"] = response.latency_ms
        event["cost_usd"] = response.cost_usd
        event["cached"] = response.cached
        self.writer.append(event)
        return response

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from a11y_pipeline.models.client import ModelClient, ModelRequest, ModelResponse


def _canonical_request(request: ModelRequest) -> str:
    # Serialize request fields without embedding image bytes
    messages: list[dict[str, Any]] = []
    for message in request.messages:
        messages.append(
            {
                "role": message.role,
                "text": message.text,
                "has_image": message.image_png is not None,
            }
        )
    payload = {
        "system": request.system,
        "messages": messages,
        "output_schema": request.output_schema.model_json_schema(),
        "element_id": request.element_id,
        "max_tokens": request.max_tokens,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _image_hashes(request: ModelRequest) -> list[str]:
    # Hash each image in message order
    hashes: list[str] = []
    for message in request.messages:
        if message.image_png is not None:
            hashes.append(hashlib.sha256(message.image_png).hexdigest())
    return hashes


def cache_key(request: ModelRequest) -> str:
    # Key cache entries by model prompt request and images
    digest = hashlib.sha256()
    digest.update(request.model.encode("utf-8"))
    digest.update(b"\0")
    digest.update(request.prompt_version.encode("utf-8"))
    digest.update(b"\0")
    digest.update(_canonical_request(request).encode("utf-8"))
    for image_hash in _image_hashes(request):
        digest.update(b"\0")
        digest.update(image_hash.encode("ascii"))
    return digest.hexdigest()


class DiskModelCache:
    def __init__(self, directory: Path) -> None:
        # Store cache entries below the configured directory
        self.directory = directory

    def get(self, request: ModelRequest) -> ModelResponse | None:
        # Load and validate one cached response
        path = self.directory / f"{cache_key(request)}.json"
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            output = request.output_schema.model_validate(payload["output"])
            return ModelResponse(
                output=output,
                raw_text=payload["raw_text"],
                input_tokens=payload["input_tokens"],
                output_tokens=payload["output_tokens"],
                latency_ms=payload["latency_ms"],
                cost_usd=0.0,
                cached=True,
            )
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError, ValidationError):
            return None

    def put(self, request: ModelRequest, response: ModelResponse) -> None:
        # Write one response atomically as stable JSON
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{cache_key(request)}.json"
        temporary_path = path.with_suffix(".tmp")
        payload = {
            "output": response.output.model_dump(mode="json"),
            "raw_text": response.raw_text,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "latency_ms": response.latency_ms,
            "cost_usd": response.cost_usd,
        }
        text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        temporary_path.write_text(text, encoding="utf-8")
        temporary_path.replace(path)


class CachedModelClient:
    def __init__(self, client: ModelClient, cache: DiskModelCache) -> None:
        # Store the wrapped client and disk cache
        self.client = client
        self.cache = cache

    def complete_structured(self, request: ModelRequest) -> ModelResponse:
        # Serve a cache hit or store a fresh model response
        cached_response = self.cache.get(request)
        if cached_response is not None:
            return cached_response
        response = self.client.complete_structured(request)
        self.cache.put(request, response)
        return response

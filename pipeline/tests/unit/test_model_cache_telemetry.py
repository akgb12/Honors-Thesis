import json

import pytest
from pydantic import BaseModel

from a11y_pipeline.models.cache import CachedModelClient, DiskModelCache, cache_key
from a11y_pipeline.models.client import ModelMessage, ModelRequest
from a11y_pipeline.models.fake import FakeModelClient
from a11y_pipeline.telemetry import (
    REDACTED,
    TelemetryModelClient,
    TelemetryWriter,
    redact_secret_fields,
)


class Description(BaseModel):
    alt_text: str


def make_request(image_png: bytes | None = None) -> ModelRequest:
    # Build a cacheable request with optional image content
    return ModelRequest(
        model="test-model",
        system="Describe the figure",
        messages=[ModelMessage(role="user", text="Figure", image_png=image_png)],
        output_schema=Description,
        prompt_version="test_v1",
        element_id="slide_01/figure_01",
        max_tokens=100,
    )


def test_disk_cache_miss_then_hit(tmp_path) -> None:
    # Call the model once and serve the next response from disk
    fake = FakeModelClient(
        scripts={"slide_01/figure_01": [{"alt_text": "A five part diagram"}]},
    )
    client = CachedModelClient(fake, DiskModelCache(tmp_path / "cache"))
    request = make_request(b"png bytes")

    miss = client.complete_structured(request)
    hit = client.complete_structured(request)

    assert miss.cached is False
    assert hit.cached is True
    assert hit.output.alt_text == "A five part diagram"
    assert hit.cost_usd == 0.0
    assert len(fake.requests) == 1
    assert len(list((tmp_path / "cache").glob("*.json"))) == 1


def test_cache_key_changes_with_image_content() -> None:
    # Keep visually different image requests in separate entries
    first = make_request(b"first image")
    second = make_request(b"second image")

    assert cache_key(first) != cache_key(second)


def test_corrupt_cache_entry_is_treated_as_miss(tmp_path) -> None:
    # Ignore invalid cache data and replace it from the model
    request = make_request()
    cache = DiskModelCache(tmp_path / "cache")
    cache.directory.mkdir()
    path = cache.directory / f"{cache_key(request)}.json"
    path.write_text("{not json", encoding="utf-8")
    fake = FakeModelClient(
        scripts={"slide_01/figure_01": [{"alt_text": "Recovered response"}]},
    )

    response = CachedModelClient(fake, cache).complete_structured(request)

    assert response.output.alt_text == "Recovered response"
    assert len(fake.requests) == 1
    assert json.loads(path.read_text(encoding="utf-8"))["output"]["alt_text"] == (
        "Recovered response"
    )


def test_redaction_handles_telemetry_and_manifest_shaped_data() -> None:
    # Remove credential fields while preserving model token counts
    data = {
        "api_key": "credential",
        "nested": {
            "password": "credential",
            "access_token": "credential",
            "input_tokens": 14,
        },
        "items": [{"DJANGO_SECRET_KEY": "credential"}],
    }

    redacted = redact_secret_fields(data)

    assert redacted["api_key"] == REDACTED
    assert redacted["nested"]["password"] == REDACTED
    assert redacted["nested"]["access_token"] == REDACTED
    assert redacted["nested"]["input_tokens"] == 14
    assert redacted["items"][0]["DJANGO_SECRET_KEY"] == REDACTED


def test_telemetry_appends_one_line_per_successful_call(tmp_path) -> None:
    # Append complete call metadata without model request content
    fake = FakeModelClient(
        scripts={
            "slide_01/figure_01": [
                {"alt_text": "First response"},
                {"alt_text": "Second response"},
            ]
        },
    )
    path = tmp_path / "run" / "telemetry.jsonl"
    client = TelemetryModelClient(fake, TelemetryWriter(path))
    request = make_request()

    client.complete_structured(request)
    client.complete_structured(request)

    lines = path.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    assert len(lines) == 2
    assert first["status"] == "ok"
    assert first["input_tokens"] == 12
    assert first["element_id"] == "slide_01/figure_01"
    assert "messages" not in first


def test_telemetry_records_failure_without_error_message(tmp_path) -> None:
    # Record a safe error type when a call fails
    fake = FakeModelClient()
    path = tmp_path / "telemetry.jsonl"
    client = TelemetryModelClient(fake, TelemetryWriter(path))

    with pytest.raises(LookupError):
        client.complete_structured(make_request())

    event = json.loads(path.read_text(encoding="utf-8"))
    assert event["status"] == "error"
    assert event["error_type"] == "LookupError"
    assert "error_message" not in event

import base64
import json

import httpx
import pytest
from pydantic import BaseModel, ValidationError

from a11y_pipeline.config import Settings
from a11y_pipeline.models.anthropic_client import AnthropicModelClient, MissingToolOutput
from a11y_pipeline.models.client import ModelMessage, ModelRequest


class Description(BaseModel):
    alt_text: str
    decorative: bool = False


def make_settings(model: str = "test-model") -> Settings:
    # Build complete isolated Anthropic settings for mocked tests
    return Settings(
        _env_file=None,
        model_provider="anthropic",
        anthropic_api_key="local-test-value",
        generator_model=model,
        model_input_usd_per_mtok=3.0,
        model_output_usd_per_mtok=15.0,
    )


def make_request() -> ModelRequest:
    # Build one image request for the mocked client
    return ModelRequest(
        model="test-model",
        system="Describe figures accessibly",
        messages=[
            ModelMessage(
                role="user",
                text="Describe this diagram",
                image_png=b"png image bytes",
            )
        ],
        output_schema=Description,
        prompt_version="figure_description_v1",
        element_id="slide_01/figure_01",
        max_tokens=250,
    )


def anthropic_response(tool_input: dict[str, object]) -> dict[str, object]:
    # Build an SDK compatible tool use response
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "test-model",
        "content": [
            {
                "type": "tool_use",
                "id": "tool_test",
                "name": "submit",
                "input": tool_input,
            }
        ],
        "stop_reason": "tool_use",
        "stop_sequence": None,
        "usage": {
            "input_tokens": 100,
            "output_tokens": 20,
        },
    }


def test_anthropic_client_requests_tool_and_sends_png_block(respx_mock) -> None:
    # Verify the SDK request and parse mocked tool input
    route = respx_mock.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(
            200,
            json=anthropic_response(
                {"alt_text": "Five folds with the third selected.", "decorative": False}
            ),
        )
    )
    client = AnthropicModelClient(make_settings())

    response = client.complete_structured(make_request())

    assert route.called
    sent = json.loads(route.calls[0].request.content)
    assert sent["model"] == "test-model"
    assert sent["tool_choice"] == {"type": "auto"}
    assert "submit tool exactly once" in sent["system"]
    assert sent["system"].startswith("Describe figures accessibly")
    assert "thinking" not in sent
    assert sent["tools"][0]["name"] == "submit"
    assert sent["tools"][0]["input_schema"]["required"] == ["alt_text"]
    blocks = sent["messages"][0]["content"]
    assert blocks[0] == {"type": "text", "text": "Describe this diagram"}
    assert blocks[1]["type"] == "image"
    assert blocks[1]["source"]["media_type"] == "image/png"
    assert blocks[1]["source"]["data"] == base64.b64encode(b"png image bytes").decode("ascii")
    assert response.output.alt_text == "Five folds with the third selected."
    assert response.input_tokens == 100
    assert response.output_tokens == 20
    assert response.cost_usd == pytest.approx(0.0006)


def test_anthropic_client_disables_thinking_for_sonnet_five_five(respx_mock) -> None:
    # Keep the small output budget for the answer on models that think by default
    route = respx_mock.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(200, json=anthropic_response({"alt_text": "A diagram."}))
    )
    client = AnthropicModelClient(make_settings("claude-sonnet-5-5"))

    client.complete_structured(make_request())

    sent = json.loads(route.calls[0].request.content)
    assert sent["model"] == "claude-sonnet-5-5"
    assert sent["thinking"] == {"type": "between_tools"}
    assert sent["tool_choice"] == {"type": "auto"}


def test_anthropic_client_reports_stop_reason_when_tool_is_missing(respx_mock) -> None:
    # A text-only reply (for example after hitting max tokens) names its stop reason
    body = {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "test-model",
        "content": [{"type": "text", "text": "cut off"}],
        "stop_reason": "max_tokens",
        "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }
    respx_mock.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(200, json=body)
    )
    client = AnthropicModelClient(make_settings())

    with pytest.raises(MissingToolOutput, match="max_tokens"):
        client.complete_structured(make_request())


def test_anthropic_client_rejects_malformed_tool_input(respx_mock) -> None:
    # Reject a successful HTTP response that violates the output contract
    route = respx_mock.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(
            200,
            json=anthropic_response({"decorative": False}),
        )
    )
    client = AnthropicModelClient(make_settings())

    with pytest.raises(ValidationError, match="alt_text"):
        client.complete_structured(make_request())

    assert route.call_count == 1


def test_anthropic_client_refuses_fake_settings() -> None:
    # Prevent construction without credentials and model prices
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        AnthropicModelClient(Settings(_env_file=None))

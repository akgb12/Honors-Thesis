import base64
import json

import httpx
import pytest
from pydantic import BaseModel

from a11y_pipeline.config import Settings
from a11y_pipeline.models.anthropic_client import AnthropicModelClient, MissingStructuredOutput
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


def anthropic_response(
    payload: dict[str, object],
    stop_reason: str = "end_turn",
) -> dict[str, object]:
    # Build an SDK compatible response whose text block holds structured JSON
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "test-model",
        "content": [{"type": "text", "text": json.dumps(payload)}],
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": 100,
            "output_tokens": 20,
        },
    }


def test_anthropic_client_requests_schema_output_and_sends_png_block(respx_mock) -> None:
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
    assert sent["system"] == "Describe figures accessibly"
    assert "tools" not in sent
    assert "tool_choice" not in sent
    assert "thinking" not in sent
    output_format = sent["output_config"]["format"]
    assert output_format["type"] == "json_schema"
    assert output_format["schema"]["required"] == ["alt_text"]
    assert output_format["schema"]["additionalProperties"] is False
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
    assert sent["output_config"]["format"]["type"] == "json_schema"


def test_anthropic_client_reports_stop_reason_and_usage_when_json_is_cut_off(respx_mock) -> None:
    # Truncated JSON names its stop reason and still carries the billed usage
    body = anthropic_response({}, stop_reason="max_tokens")
    body["content"] = [{"type": "text", "text": '{"alt_text": "A diag'}]
    respx_mock.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(200, json=body)
    )
    client = AnthropicModelClient(make_settings())

    with pytest.raises(MissingStructuredOutput, match="max_tokens") as error:
        client.complete_structured(make_request())

    assert error.value.input_tokens == 100
    assert error.value.output_tokens == 20
    assert error.value.cost_usd == pytest.approx(0.0006)


def test_anthropic_client_rejects_malformed_structured_output(respx_mock) -> None:
    # Reject a successful HTTP response that violates the output contract
    route = respx_mock.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(
            200,
            json=anthropic_response({"decorative": False}),
        )
    )
    client = AnthropicModelClient(make_settings())

    with pytest.raises(MissingStructuredOutput, match="alt_text") as error:
        client.complete_structured(make_request())

    assert error.value.input_tokens == 100

    assert route.call_count == 1


def test_anthropic_client_refuses_fake_settings() -> None:
    # Prevent construction without credentials and model prices
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        AnthropicModelClient(Settings(_env_file=None))

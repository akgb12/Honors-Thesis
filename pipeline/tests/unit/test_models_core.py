import pytest
from pydantic import BaseModel, ValidationError

from a11y_pipeline.budget import Budget, BudgetedModelClient, BudgetExceeded
from a11y_pipeline.config import Settings
from a11y_pipeline.models.client import ModelMessage, ModelRequest
from a11y_pipeline.models.fake import FakeModelClient, FakeScriptResponse
from a11y_pipeline.models.pricing import ModelPricing


class Description(BaseModel):
    alt_text: str


def make_request(element_id: str = "slide_01/figure_01", max_tokens: int = 100) -> ModelRequest:
    # Build a small structured request for model tests
    return ModelRequest(
        model="test-model",
        system="Return a description",
        messages=[ModelMessage(role="user", text="Describe the figure")],
        output_schema=Description,
        prompt_version="test_v1",
        element_id=element_id,
        max_tokens=max_tokens,
    )


def test_settings_default_to_fake_without_model_prices() -> None:
    # Confirm local development starts without real model settings
    settings = Settings(_env_file=None)

    assert settings.model_provider == "fake"
    assert settings.anthropic_api_key is None


@pytest.mark.parametrize(
    ("values", "message"),
    [
        (
            {
                "model_provider": "anthropic",
                "model_input_usd_per_mtok": 1.0,
                "model_output_usd_per_mtok": 2.0,
            },
            "ANTHROPIC_API_KEY",
        ),
        (
            {
                "model_provider": "anthropic",
                "anthropic_api_key": "local-test-value",
                "model_output_usd_per_mtok": 2.0,
            },
            "MODEL_INPUT_USD_PER_MTOK",
        ),
        (
            {
                "model_provider": "anthropic",
                "anthropic_api_key": "local-test-value",
                "model_input_usd_per_mtok": 1.0,
            },
            "MODEL_OUTPUT_USD_PER_MTOK",
        ),
        (
            {
                "model_provider": "anthropic",
                "anthropic_api_key": "local-test-value",
                "model_input_usd_per_mtok": "",
                "model_output_usd_per_mtok": "",
            },
            "MODEL_INPUT_USD_PER_MTOK",
        ),
    ],
)
def test_settings_refuse_incomplete_anthropic_configuration(
    values: dict[str, object],
    message: str,
) -> None:
    # Refuse real model mode without every safety value
    with pytest.raises(ValidationError, match=message):
        Settings(_env_file=None, **values)


def test_settings_hide_anthropic_key_from_representation() -> None:
    # Keep credentials out of settings diagnostics
    marker = "local-test-value"
    settings = Settings(
        _env_file=None,
        model_provider="anthropic",
        anthropic_api_key=marker,
        model_input_usd_per_mtok=1.0,
        model_output_usd_per_mtok=2.0,
    )

    assert marker not in repr(settings)
    assert marker not in str(settings)


def test_settings_hide_anthropic_key_from_validation_errors() -> None:
    # Keep credentials out of incomplete configuration errors
    marker = "local-test-value"

    with pytest.raises(ValidationError) as error:
        Settings(
            _env_file=None,
            model_provider="anthropic",
            anthropic_api_key=marker,
        )

    assert marker not in str(error.value)


def test_fake_model_client_runs_weak_then_good_script() -> None:
    # Return repair demonstration answers in stable order
    client = FakeModelClient.weak_then_good(
        "slide_01/figure_01",
        {"alt_text": "Five boxes in a row, one is blue."},
        {"alt_text": "Five folds with the third fold selected for testing."},
    )
    request = make_request()

    first = client.complete_structured(request)
    second = client.complete_structured(request)

    assert first.output.alt_text == "Five boxes in a row, one is blue."
    assert second.output.alt_text == "Five folds with the third fold selected for testing."
    assert first.input_tokens == 12
    assert len(client.requests) == 2


def test_fake_model_client_uses_default_generator() -> None:
    # Generate deterministic responses for elements without scripts
    def generate(request: ModelRequest) -> FakeScriptResponse:
        # Include the requested element in the generated description
        return FakeScriptResponse(
            output={"alt_text": f"Description for {request.element_id}"},
            input_tokens=4,
            output_tokens=5,
        )

    client = FakeModelClient(default_generator=generate)

    response = client.complete_structured(make_request("slide_02/figure_01"))

    assert response.output.alt_text == "Description for slide_02/figure_01"
    assert response.input_tokens == 4
    assert response.output_tokens == 5


def test_budget_refuses_call_before_client_execution() -> None:
    # Stop an estimated call before invoking the wrapped client
    client = FakeModelClient(
        scripts={"slide_01/figure_01": [{"alt_text": "Unused"}]},
    )
    budget = Budget(cap_usd=0.000001)
    pricing = ModelPricing(input_usd_per_mtok=10.0, output_usd_per_mtok=20.0)
    wrapped = BudgetedModelClient(client, budget, pricing)

    with pytest.raises(BudgetExceeded, match="would exceed"):
        wrapped.complete_structured(make_request(max_tokens=1000))

    assert client.requests == []
    assert budget.spent_usd == 0.0


def test_budget_accumulates_actual_cost() -> None:
    # Add the real response cost after an allowed call
    class CostingClient:
        def complete_structured(self, request: ModelRequest):
            # Reuse a fake response with a controlled cost
            response = FakeModelClient(
                scripts={request.element_id: [{"alt_text": "A diagram"}]}
            ).complete_structured(request)
            return response.model_copy(update={"cost_usd": 0.25})

    budget = Budget(cap_usd=1.0)
    pricing = ModelPricing(input_usd_per_mtok=1.0, output_usd_per_mtok=1.0)
    wrapped = BudgetedModelClient(CostingClient(), budget, pricing)

    wrapped.complete_structured(make_request(max_tokens=10))

    assert budget.spent_usd == 0.25

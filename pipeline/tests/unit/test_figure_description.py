import json

from a11y_pipeline.analysis.needs import Task
from a11y_pipeline.budget import Budget, BudgetedModelClient
from a11y_pipeline.capabilities.base import FigureDescriptionInput
from a11y_pipeline.capabilities.figure_description import (
    PROMPT_VERSION,
    FigureDescriptionCapability,
)
from a11y_pipeline.models.fake import FakeModelClient, FakeScriptResponse
from a11y_pipeline.models.pricing import ModelPricing
from a11y_pipeline.routing.router import route
from a11y_pipeline.telemetry import TelemetryModelClient, TelemetryWriter


def _capability_input(subtype: str = "diagram") -> FigureDescriptionInput:
    # Build one source neutral figure input
    return FigureDescriptionInput(
        element_id="slide_03/figure_01",
        subtype=subtype,
        image_png=b"\x89PNG\r\n\x1a\ncrop",
        source_code="\\begin{tikzpicture}\\node {Fold 1};\\end{tikzpicture}",
        visible_labels=["Fold 1", "Fold 2"],
        slide_title="Cross validation",
        nearby_text=["Each fold serves as the test set once."],
    )


def _patch_values(result) -> dict[str, object]:
    # Index patch values by path
    values: dict[str, object] = {}
    for patch in result.patches:
        values[patch.path] = patch.value
    return values


def _wrapped_client(fake: FakeModelClient, telemetry_path):
    # Add budget and telemetry controls to the fake client
    budget = Budget(cap_usd=1.0)
    pricing = ModelPricing(input_usd_per_mtok=1.0, output_usd_per_mtok=1.0)
    budgeted = BudgetedModelClient(fake, budget, pricing)
    client = TelemetryModelClient(budgeted, TelemetryWriter(telemetry_path))
    return client, budget


def test_figure_description_success_builds_request_and_patches(tmp_path) -> None:
    # Return complete patches and provenance after one valid response
    fake = FakeModelClient(
        scripts={
            "slide_03/figure_01": [
                FakeScriptResponse(
                    output={
                        "alt_text": "Five folds with one fold selected for testing.",
                        "extended_description": "The selection advances across the folds.",
                        "decorative": False,
                    },
                    input_tokens=21,
                    output_tokens=13,
                )
            ]
        }
    )
    client, _budget = _wrapped_client(fake, tmp_path / "telemetry.jsonl")
    capability = FigureDescriptionCapability(
        client,
        model="test-model",
    )

    result = capability.run(_capability_input(), run_id="run-1", round_number=0)

    values = _patch_values(result)
    assert values["accessibility.alt_text"] == ("Five folds with one fold selected for testing.")
    assert values["accessibility.extended_description"] == (
        "The selection advances across the folds."
    )
    assert values["accessibility.decorative_suggested"] is False
    assert values["accessibility.status"] == "model_generated"
    assert "classification" not in values
    assert result.history is not None
    assert result.history.input_tokens == 21
    assert result.history.output_tokens == 13
    assert result.history.model == "test-model"
    assert result.history.prompt_version == PROMPT_VERSION
    request = fake.requests[0]
    context = json.loads(request.messages[0].text.split("\n", 1)[1])
    assert request.messages[0].image_png == _capability_input().image_png
    assert context["source_code"].startswith("\\begin{tikzpicture}")
    assert context["visible_labels"] == ["Fold 1", "Fold 2"]
    assert context["slide_title"] == "Cross validation"
    assert context["nearby_text"] == ["Each fold serves as the test set once."]
    image_request = capability.build_request(_capability_input("image"))
    image_context = json.loads(image_request.messages[0].text.split("\n", 1)[1])
    assert "source_code" not in image_context
    routed = route(
        [Task(element_id="slide_03/figure_01", capability="figure_description", reason="Test")]
    )
    assert routed[0].capability is FigureDescriptionCapability


def test_figure_description_retries_once_then_succeeds(tmp_path) -> None:
    # Retry one invalid structured response and keep the valid result
    fake = FakeModelClient(
        scripts={
            "slide_03/figure_01": [
                {"extended_description": None, "decorative": False},
                {"alt_text": "A regression line rises through scattered observations."},
            ]
        }
    )
    telemetry_path = tmp_path / "telemetry.jsonl"
    client, budget = _wrapped_client(fake, telemetry_path)
    capability = FigureDescriptionCapability(
        client,
        model="test-model",
    )

    result = capability.run(_capability_input("image"), run_id="run-2", round_number=1)

    assert len(fake.requests) == 2
    assert _patch_values(result)["accessibility.status"] == "model_generated"
    assert result.history is not None
    assert result.history.input_tokens == 12
    assert budget.spent_usd > 0
    lines = telemetry_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["status"] == "error"
    assert json.loads(lines[1])["status"] == "ok"


def test_figure_description_marks_failed_after_two_invalid_responses(tmp_path) -> None:
    # Mark the figure failed after the allowed retry
    fake = FakeModelClient(
        scripts={
            "slide_03/figure_01": [
                {"decorative": False},
                {"extended_description": "Missing required alt text"},
            ]
        }
    )
    telemetry_path = tmp_path / "telemetry.jsonl"
    client, budget = _wrapped_client(fake, telemetry_path)
    capability = FigureDescriptionCapability(
        client,
        model="test-model",
    )

    result = capability.run(_capability_input(), run_id="run-3")

    assert len(fake.requests) == 2
    assert len(result.patches) == 1
    assert result.patches[0].path == "accessibility.status"
    assert result.patches[0].value == "failed"
    assert result.history is None
    assert budget.spent_usd > 0
    lines = telemetry_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["status"] == "error"
    assert json.loads(lines[1])["status"] == "error"

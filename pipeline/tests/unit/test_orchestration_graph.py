import json
from pathlib import Path

from a11y_pipeline.capabilities.base import FigureDescriptionInput
from a11y_pipeline.config import Settings
from a11y_pipeline.ir.ids import fingerprint_source
from a11y_pipeline.ir.models import (
    Accessibility,
    Container,
    DocumentIR,
    Element,
    Fidelity,
    SourceRef,
)
from a11y_pipeline.models.fake import FakeModelClient
from a11y_pipeline.orchestration.graph import run_pipeline
from a11y_pipeline.orchestration.nodes import analyze_needs_node
from a11y_pipeline.orchestration.state import RunState

CV_ID = "slide_01/figure_01"
REGRESSION_ID = "slide_02/figure_01"
WEAK = {"alt_text": "Five boxes in a row, one is blue."}
GOOD_CV = {
    "alt_text": (
        "Five-fold cross-validation uses five folds with the third position as the test fold."
    )
}
GOOD_REGRESSION = {"alt_text": "A fitted regression line rises through the observed points."}


def _figure(
    element_id: str,
    parent_id: str,
    subtype: str,
    concepts: list[str],
) -> Element:
    # Build one orchestration figure
    raw = f"figure {element_id}"
    return Element(
        id=element_id,
        semantic_type="figure",
        subtype=subtype,
        parent_id=parent_id,
        fingerprint=fingerprint_source(raw),
        source=SourceRef(
            file="main.tex",
            line_start=1,
            line_end=1,
            char_start=0,
            char_end=len(raw),
            native_type=subtype,
            raw=raw,
        ),
        accessibility=Accessibility(role="Figure", status="needs_description"),
        fidelity=Fidelity(required_concepts=concepts),
    )


def _document(include_regression: bool = False) -> DocumentIR:
    # Build a frozen document for orchestration tests
    cv = _figure(
        CV_ID,
        "slide_01",
        "diagram",
        ["sequence:5:Fold", "label:Test"],
    )
    elements = {CV_ID: cv}
    containers = [
        Container(id="slide_01", kind="slide", element_ids=[CV_ID]),
    ]
    if include_regression:
        regression = _figure(REGRESSION_ID, "slide_02", "image", [])
        elements[REGRESSION_ID] = regression
        containers.append(
            Container(
                id="slide_02",
                kind="slide",
                element_ids=[REGRESSION_ID],
            )
        )
    return DocumentIR(
        document_id="orchestration12",
        source_format="tex-beamer",
        main_file="main.tex",
        containers=containers,
        elements=elements,
    )


def _inputs(include_regression: bool = False) -> dict[str, FigureDescriptionInput]:
    # Build prepared capability inputs
    values = {
        CV_ID: FigureDescriptionInput(
            element_id=CV_ID,
            subtype="diagram",
            image_png=b"cv png",
            source_code="five folds with a test label",
            visible_labels=["Fold 1", "Fold 2", "Test", "Fold 4", "Fold 5"],
            slide_title="Cross validation",
            nearby_text=[],
        )
    }
    if include_regression:
        values[REGRESSION_ID] = FigureDescriptionInput(
            element_id=REGRESSION_ID,
            subtype="image",
            image_png=b"regression png",
            source_code=None,
            visible_labels=[],
            slide_title="Regression",
            nearby_text=[],
        )
    return values


def _settings(**updates: object) -> Settings:
    # Build isolated fake settings
    values: dict[str, object] = {
        "_env_file": None,
        "model_provider": "fake",
    }
    values.update(updates)
    return Settings(**values)


def _telemetry(path: Path) -> list[dict[str, object]]:
    # Read stable telemetry events
    events: list[dict[str, object]] = []
    if not path.exists():
        return events
    for line in path.read_text(encoding="utf-8").splitlines():
        events.append(json.loads(line))
    return events


def test_weak_then_good_repairs_only_cv_and_stops(tmp_path: Path) -> None:
    # Repair only the failing cross validation figure
    fake = FakeModelClient(
        scripts={
            CV_ID: [WEAK, GOOD_CV],
            REGRESSION_ID: [GOOD_REGRESSION],
        }
    )
    telemetry_path = tmp_path / "telemetry.jsonl"
    base_ir = _document(include_regression=True)

    state = run_pipeline(
        model_client=fake,
        effort="medium",
        settings=_settings(),
        run_id="weak-good",
        telemetry_path=telemetry_path,
        base_ir=base_ir,
        figure_inputs=_inputs(include_regression=True),
    )

    assert state.stop_reason == "nothing_failing"
    assert state.current_round == 1
    assert state.repair_counts == {CV_ID: 1}
    assert state.selected_candidate_id == "c2"
    assert state.final_ir is not None
    assert state.final_ir.elements[CV_ID].accessibility.alt_text == GOOD_CV["alt_text"]
    assert (
        state.final_ir.elements[REGRESSION_ID].accessibility.alt_text
        == (GOOD_REGRESSION["alt_text"])
    )
    assert base_ir.elements[CV_ID].accessibility.alt_text is None
    assert base_ir.elements[CV_ID].accessibility.status == "needs_description"
    repair_rounds: list[int] = []
    for patch in state.candidates[2].patches:
        if patch.element_id == CV_ID and patch.path == "accessibility.alt_text":
            repair_rounds.append(patch.round)
    assert repair_rounds == [0, 1]
    requested_ids: list[str] = []
    for request in fake.requests:
        requested_ids.append(request.element_id)
    assert requested_ids == [CV_ID, REGRESSION_ID, CV_ID]
    events = _telemetry(telemetry_path)
    assert len(events) == 3
    for index, element_id in enumerate(requested_ids):
        event = events[index]
        assert event["element_id"] == element_id
        assert event["status"] == "ok"
        assert event["input_tokens"] == 12
        assert event["output_tokens"] == 8
        assert event["cost_usd"] == 0.0
        assert event["cached"] is False
        assert event["model"] == "claude-sonnet-5-5"
        assert event["prompt_version"] == "figure_description_v1"
        assert event["max_tokens"] == 1000
        assert "latency_ms" in event
        assert "timestamp" in event


def test_always_weak_stops_after_two_repairs_with_review(tmp_path: Path) -> None:
    # Exhaust two repairs and preserve the deterministic fallback
    fake = FakeModelClient(scripts={CV_ID: [WEAK, WEAK, WEAK]})

    state = run_pipeline(
        model_client=fake,
        effort="medium",
        settings=_settings(),
        run_id="always-weak",
        telemetry_path=tmp_path / "telemetry.jsonl",
        base_ir=_document(),
        figure_inputs=_inputs(),
    )

    assert state.stop_reason == "round_cap"
    assert state.current_round == 2
    assert state.repair_counts == {CV_ID: 2}
    assert len(fake.requests) == 3
    assert len(state.candidates) == 4
    assert state.selected_candidate_id == "c0"
    assert state.final_ir is not None
    final = state.final_ir.elements[CV_ID]
    assert final.accessibility.alt_text is None
    assert final.accessibility.status == "needs_review"


def test_baseline_runs_initial_pass_without_repairs(tmp_path: Path) -> None:
    # Keep round zero outside the baseline repair cap
    fake = FakeModelClient(scripts={CV_ID: [WEAK, GOOD_CV]})

    state = run_pipeline(
        model_client=fake,
        effort="baseline",
        settings=_settings(),
        run_id="baseline",
        telemetry_path=tmp_path / "telemetry.jsonl",
        base_ir=_document(),
        figure_inputs=_inputs(),
    )

    assert state.stop_reason == "round_cap"
    assert state.current_round == 0
    assert state.repair_counts == {}
    assert len(fake.requests) == 1
    assert len(state.candidates) == 2


def test_budget_cap_stops_before_real_fake_call(tmp_path: Path) -> None:
    # Stop when the next estimated call exceeds the cap
    fake = FakeModelClient(scripts={CV_ID: [WEAK]})
    settings = _settings(
        run_dollar_cap_medium=0.0,
        model_input_usd_per_mtok=1000.0,
        model_output_usd_per_mtok=1000.0,
    )
    telemetry_path = tmp_path / "telemetry.jsonl"

    state = run_pipeline(
        model_client=fake,
        effort="medium",
        settings=settings,
        run_id="budget",
        telemetry_path=telemetry_path,
        base_ir=_document(),
        figure_inputs=_inputs(),
    )

    assert state.stop_reason == "budget_cap"
    assert state.budget_exhausted
    assert fake.requests == []
    events = _telemetry(telemetry_path)
    assert len(events) == 1
    assert events[0]["status"] == "error"
    assert events[0]["error_type"] == "BudgetExceeded"
    assert events[0]["element_id"] == CV_ID


def test_no_accepted_improvement_stops_after_regression(tmp_path: Path) -> None:
    # Stop when a repair candidate regresses
    partial = {"alt_text": "Five folds are shown."}
    contradiction = {"alt_text": "Four folds are shown with a test fold."}
    fake = FakeModelClient(scripts={CV_ID: [partial, contradiction]})

    state = run_pipeline(
        model_client=fake,
        effort="medium",
        settings=_settings(),
        run_id="regression",
        telemetry_path=tmp_path / "telemetry.jsonl",
        base_ir=_document(),
        figure_inputs=_inputs(),
    )

    assert state.stop_reason == "no_accepted_improvement"
    assert state.current_round == 1
    assert len(fake.requests) == 2
    assert state.selected_candidate_id == "c0"


def test_seed_weak_skips_initial_model_call(tmp_path: Path) -> None:
    # Seed fixed weak text without telemetry or a model request
    fake = FakeModelClient(scripts={CV_ID: [GOOD_CV]})
    telemetry_path = tmp_path / "telemetry.jsonl"

    state = run_pipeline(
        model_client=fake,
        effort="medium",
        settings=_settings(),
        run_id="seed-weak",
        telemetry_path=telemetry_path,
        base_ir=_document(),
        figure_inputs=_inputs(),
        seed_weak_element_id=CV_ID,
    )

    assert state.stop_reason == "nothing_failing"
    assert len(fake.requests) == 1
    assert fake.requests[0].element_id == CV_ID
    events = _telemetry(telemetry_path)
    assert len(events) == 1
    assert events[0]["element_id"] == CV_ID
    assert state.candidates[1].patches[0].value == "Five boxes in a row, one is blue."


def test_plain_node_returns_partial_update_without_mutation(tmp_path: Path) -> None:
    # Call a graph node directly as a plain function
    document = _document()
    state = RunState(
        run_id="direct",
        config=_settings(),
        effort="low",
        base_ir=document,
        telemetry_path=tmp_path / "telemetry.jsonl",
    )

    update = analyze_needs_node(state)

    assert update["current_round"] == 0
    assert update["pending_element_ids"] == [CV_ID]
    assert state.tasks == []
    assert state.base_ir is document

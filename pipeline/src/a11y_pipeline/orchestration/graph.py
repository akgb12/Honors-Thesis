from pathlib import Path
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from a11y_pipeline.budget import Budget, BudgetedModelClient
from a11y_pipeline.capabilities.base import FigureDescriptionInput
from a11y_pipeline.config import Settings
from a11y_pipeline.ir.models import DocumentIR
from a11y_pipeline.models.client import ModelClient
from a11y_pipeline.models.pricing import ModelPricing
from a11y_pipeline.orchestration.effort import Effort, dollar_cap
from a11y_pipeline.orchestration.nodes import (
    analyze_needs_node,
    build_c0_node,
    build_ir_node,
    compile_and_map_node,
    decide_node,
    evaluate_node,
    finalize_blocked_node,
    finalize_node,
    ingest_node,
    preflight_node,
    prepare_repair_node,
    route_node,
    run_capabilities_node,
    synthesize_node,
)
from a11y_pipeline.orchestration.state import RunState
from a11y_pipeline.telemetry import TelemetryModelClient, TelemetryWriter


def build_graph():
    # Build the typed Mark 1 orchestration graph
    graph = StateGraph(RunState)
    graph.add_node("ingest", ingest_node)
    graph.add_node("preflight", preflight_node)
    graph.add_node("finalize_blocked", finalize_blocked_node)
    graph.add_node("build_ir", build_ir_node)
    graph.add_node("compile_and_map", compile_and_map_node)
    graph.add_node("build_c0", build_c0_node)
    graph.add_node("analyze_needs", analyze_needs_node)
    graph.add_node("route", route_node)
    graph.add_node("run_capabilities", run_capabilities_node)
    graph.add_node("synthesize", synthesize_node)
    graph.add_node("evaluate", evaluate_node)
    graph.add_node("decide", decide_node)
    graph.add_node("prepare_repair", prepare_repair_node)
    graph.add_node("finalize", finalize_node)
    graph.add_edge(START, "ingest")
    graph.add_edge("ingest", "preflight")
    graph.add_conditional_edges(
        "preflight",
        _after_preflight,
        {"blocked": "finalize_blocked", "ready": "build_ir"},
    )
    graph.add_edge("finalize_blocked", END)
    graph.add_edge("build_ir", "compile_and_map")
    graph.add_edge("compile_and_map", "build_c0")
    graph.add_edge("build_c0", "analyze_needs")
    graph.add_edge("analyze_needs", "route")
    graph.add_edge("route", "run_capabilities")
    graph.add_edge("run_capabilities", "synthesize")
    graph.add_edge("synthesize", "evaluate")
    graph.add_edge("evaluate", "decide")
    graph.add_conditional_edges(
        "decide",
        _after_decide,
        {"repair": "prepare_repair", "finalize": "finalize"},
    )
    graph.add_edge("prepare_repair", "route")
    graph.add_edge("finalize", END)
    return graph.compile()


def run_pipeline(
    *,
    model_client: ModelClient,
    effort: Effort = "medium",
    settings: Settings | None = None,
    run_id: str | None = None,
    telemetry_path: Path | None = None,
    base_ir: DocumentIR | None = None,
    figure_inputs: dict[str, FigureDescriptionInput] | None = None,
    input_path: Path | None = None,
    main_file: str | None = None,
    seed_weak_element_id: str | None = None,
    adapter_name: str = "tex-beamer",
) -> RunState:
    # Run one pipeline with budget and telemetry controls
    resolved_settings = settings
    if resolved_settings is None:
        resolved_settings = Settings()
    resolved_run_id = run_id or uuid4().hex[:12]
    resolved_telemetry = telemetry_path
    if resolved_telemetry is None:
        resolved_telemetry = resolved_settings.runs_dir / resolved_run_id / "telemetry.jsonl"
    budget = Budget(cap_usd=dollar_cap(effort, resolved_settings))
    input_price = resolved_settings.model_input_usd_per_mtok or 0.0
    output_price = resolved_settings.model_output_usd_per_mtok or 0.0
    pricing = ModelPricing(
        input_usd_per_mtok=input_price,
        output_usd_per_mtok=output_price,
    )
    budgeted = BudgetedModelClient(model_client, budget, pricing)
    wrapped_client = TelemetryModelClient(
        budgeted,
        TelemetryWriter(resolved_telemetry),
    )
    initial = RunState(
        run_id=resolved_run_id,
        config=resolved_settings,
        effort=effort,
        input_path=input_path,
        main_file=main_file,
        adapter_name=adapter_name,
        base_ir=base_ir,
        telemetry_path=resolved_telemetry,
        figure_inputs=figure_inputs or {},
        model_client=wrapped_client,
        budget_controller=budget,
        seed_weak_element_id=seed_weak_element_id,
    )
    result = build_graph().invoke(initial, config={"recursion_limit": 100})
    if isinstance(result, RunState):
        return result
    return RunState.model_validate(result)


def _after_preflight(state: RunState) -> str:
    # Route blocked bundles away from model work
    if state.blocked:
        return "blocked"
    return "ready"


def _after_decide(state: RunState) -> str:
    # Route active runs into repair or finalization
    if state.stop_reason is None:
        return "repair"
    return "finalize"

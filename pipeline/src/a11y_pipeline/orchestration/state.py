from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from a11y_pipeline.analysis.needs import Task
from a11y_pipeline.bundle.bundle import Bundle
from a11y_pipeline.capabilities.base import CapabilityResult, FigureDescriptionInput
from a11y_pipeline.config import Settings
from a11y_pipeline.ir.models import Candidate, DocumentIR, Issue, Patch
from a11y_pipeline.orchestration.effort import Effort
from a11y_pipeline.orchestration.stopping import StopReason
from a11y_pipeline.routing.router import RoutedTask


class RunState(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    run_id: str
    config: Settings
    effort: Effort
    input_path: Path | None = None
    main_file: str | None = None
    adapter_name: str = "tex-beamer"
    bundle: Bundle | None = None
    preflight_result: Any | None = None
    base_ir: DocumentIR | None = None
    original_pdf: Path | None = None
    marked_pdf: Path | None = None
    candidates: list[Candidate] = Field(default_factory=list)
    current_round: int = 0
    repair_counts: dict[str, int] = Field(default_factory=dict)
    budget_spent: float = 0.0
    stop_reason: StopReason | None = None
    issues: list[Issue] = Field(default_factory=list)
    telemetry_path: Path
    figure_inputs: dict[str, FigureDescriptionInput] = Field(default_factory=dict)
    model_client: Any | None = Field(default=None, exclude=True)
    budget_controller: Any | None = Field(default=None, exclude=True)
    tasks: list[Task] = Field(default_factory=list)
    routed_tasks: list[RoutedTask] = Field(default_factory=list)
    pending_element_ids: list[str] = Field(default_factory=list)
    pending_results: list[CapabilityResult] = Field(default_factory=list)
    pending_candidate: Candidate | None = None
    active_patches: list[Patch] = Field(default_factory=list)
    candidate_ir: DocumentIR | None = None
    failing_element_ids: list[str] = Field(default_factory=list)
    selected_candidate_id: str | None = None
    last_candidate_accepted: bool = True
    budget_exhausted: bool = False
    seed_weak_element_id: str | None = None
    final_ir: DocumentIR | None = None
    blocked: bool = False

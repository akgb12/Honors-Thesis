from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from a11y_pipeline.bundle.bundle import Bundle
from a11y_pipeline.capabilities.base import FigureDescriptionInput
from a11y_pipeline.ir.models import DocumentIR, Issue
from a11y_pipeline.render.pixeldiff import PixelCheck
from a11y_pipeline.synthesis.plan import OutputOperation


@dataclass(frozen=True)
class PreparedDocument:
    ir: DocumentIR
    figure_inputs: dict[str, FigureDescriptionInput]
    original_pdf: Path
    marked_pdf: Path


@dataclass(frozen=True)
class WrittenDocument:
    project_root: Path
    diff_path: Path
    issues: list[Issue]
    operations: list[OutputOperation]
    pixel_check: PixelCheck


class SourceAdapter(Protocol):
    def preflight(self, bundle: Bundle) -> Any:
        # Check bundle readiness without model work
        ...

    def build_ir(self, bundle: Bundle, preflight_result: Any) -> DocumentIR:
        # Build the source neutral document model
        ...

    def summarize(self, ir: DocumentIR) -> str:
        # Summarize one format specific parsed document
        ...

    def prepare(
        self,
        bundle: Bundle,
        ir: DocumentIR,
        run_root: Path,
        timeout_seconds: int,
    ) -> PreparedDocument:
        # Compile map and prepare capability inputs
        ...

    def write_back(
        self,
        bundle: Bundle,
        ir: DocumentIR,
        output_root: Path,
        diff_path: Path,
        verification_root: Path,
        original_pdf: Path,
        timeout_seconds: int,
    ) -> WrittenDocument:
        # Write and verify the format specific project
        ...

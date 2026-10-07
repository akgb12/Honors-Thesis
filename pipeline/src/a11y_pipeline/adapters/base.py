from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from a11y_pipeline.bundle.bundle import Bundle
from a11y_pipeline.capabilities.base import FigureDescriptionInput
from a11y_pipeline.ir.models import DocumentIR


@dataclass(frozen=True)
class PreparedDocument:
    ir: DocumentIR
    figure_inputs: dict[str, FigureDescriptionInput]
    original_pdf: Path
    marked_pdf: Path


class SourceAdapter(Protocol):
    def preflight(self, bundle: Bundle) -> Any:
        # Check bundle readiness without model work
        ...

    def build_ir(self, bundle: Bundle, preflight_result: Any) -> DocumentIR:
        # Build the source neutral document model
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

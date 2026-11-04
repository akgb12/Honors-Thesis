import shutil
from pathlib import Path
from typing import Any

from a11y_pipeline.adapters.base import PreparedDocument, SourceAdapter, WrittenDocument
from a11y_pipeline.adapters.tex_beamer.aux_reader import apply_aux_mapping, read_aux
from a11y_pipeline.adapters.tex_beamer.builder import build, summarize
from a11y_pipeline.adapters.tex_beamer.compile import compile_project
from a11y_pipeline.adapters.tex_beamer.markers import inject_markers
from a11y_pipeline.adapters.tex_beamer.parser import parse
from a11y_pipeline.adapters.tex_beamer.preflight import preflight
from a11y_pipeline.adapters.tex_beamer.working_copy import create_working_copies
from a11y_pipeline.adapters.tex_beamer.writer import verify_updated_project, write_updated_project
from a11y_pipeline.bundle.bundle import Bundle
from a11y_pipeline.capabilities.base import FigureDescriptionInput
from a11y_pipeline.evaluation.concepts import (
    build_figure_concepts,
    infer_tikz_labels,
)
from a11y_pipeline.evaluation.hidden_labels import detect_figure_hidden_labels
from a11y_pipeline.ir.models import DocumentIR, Element
from a11y_pipeline.render.crop import crop_pdf_bbox
from a11y_pipeline.render.pixeldiff import compare_pdf_pixels, visual_change_issues


class TexBeamerAdapter:
    def preflight(self, bundle: Bundle) -> Any:
        # Check a Beamer project before model work
        return preflight(bundle)

    def build_ir(self, bundle: Bundle, preflight_result: Any) -> DocumentIR:
        # Parse Beamer source into canonical records
        return build(parse(bundle), preflight_result)

    def summarize(self, ir: DocumentIR) -> str:
        # Summarize parsed Beamer elements
        return summarize(ir)

    def prepare(
        self,
        bundle: Bundle,
        ir: DocumentIR,
        run_root: Path,
        timeout_seconds: int,
    ) -> PreparedDocument:
        # Compile map and prepare Beamer figure inputs
        working_ir = ir.model_copy(deep=True)
        copies = create_working_copies(bundle, working_ir, run_root / "work")
        inject_markers(working_ir, copies.marked, run_root / "injection_table.json")
        original = compile_project(copies.original, bundle.main_file, timeout_seconds)
        marked = compile_project(copies.marked, bundle.main_file, timeout_seconds)
        mapped = apply_aux_mapping(working_ir, read_aux(marked.aux_path))
        pixel_check = compare_pdf_pixels(original.pdf_path, marked.pdf_path)
        mapped.issues.extend(visual_change_issues(mapped, pixel_check))
        figure_inputs = _figure_inputs(mapped, original.pdf_path, run_root / "crops")
        return PreparedDocument(
            ir=mapped,
            figure_inputs=figure_inputs,
            original_pdf=original.pdf_path,
            marked_pdf=marked.pdf_path,
        )

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
        # Write and verify safe Beamer source updates
        result = write_updated_project(bundle, ir, output_root, diff_path)
        shutil.copytree(result.project_root, verification_root)
        verification = verify_updated_project(
            original_pdf,
            verification_root,
            bundle.main_file,
            timeout_seconds=timeout_seconds,
        )
        issues = list(result.issues)
        issues.extend(visual_change_issues(ir, verification.pixel_check))
        return WrittenDocument(
            project_root=result.project_root,
            diff_path=result.diff_path,
            issues=issues,
            operations=result.operations,
            pixel_check=verification.pixel_check,
        )


ADAPTER_REGISTRY: dict[str, SourceAdapter] = {
    "tex-beamer": TexBeamerAdapter(),
}


def get_adapter(name: str) -> SourceAdapter:
    # Return one registered source adapter
    adapter = ADAPTER_REGISTRY.get(name)
    if adapter is None:
        raise KeyError(f"source adapter is not registered: {name}")
    return adapter


def _figure_inputs(
    ir: DocumentIR,
    pdf_path: Path,
    crop_root: Path,
) -> dict[str, FigureDescriptionInput]:
    # Build model inputs from mapped source neutral figures
    inputs: dict[str, FigureDescriptionInput] = {}
    for element in ir.elements.values():
        if element.semantic_type != "figure":
            continue
        if element.accessibility.status != "needs_description":
            continue
        if not element.render.pages or element.render.bbox is None:
            continue
        slide_title, nearby_text = _figure_context(ir, element)
        labels = _figure_labels(element)
        visible = list(labels)
        hidden: list[str] = []
        if element.subtype == "diagram" and labels:
            detection = detect_figure_hidden_labels(pdf_path, element, labels)
            visible = detection.visible_labels
            hidden = detection.hidden_labels
        concepts = build_figure_concepts(element, nearby_text, visible, hidden)
        element.fidelity.required_concepts = list(concepts.required)
        element.fidelity.excluded_concepts = list(concepts.excluded)
        ir.issues.extend(concepts.issues)
        crop_path = crop_root / f"{element.id.replace('/', '-')}.png"
        crop_pdf_bbox(
            pdf_path,
            element.render.pages[-1],
            element.render.bbox,
            crop_path,
        )
        source_code = None
        if element.subtype == "diagram":
            source_code = element.source.raw
        inputs[element.id] = FigureDescriptionInput(
            element_id=element.id,
            subtype=element.subtype or "other",
            image_png=crop_path.read_bytes(),
            source_code=source_code,
            visible_labels=visible,
            slide_title=slide_title,
            nearby_text=nearby_text,
        )
    return inputs


def _figure_context(ir: DocumentIR, figure: Element) -> tuple[str | None, list[str]]:
    # Gather the slide title and nearby visible text
    container_id = figure.id.split("/", 1)[0]
    slide_title = None
    nearby: list[str] = []
    container = None
    for candidate in ir.containers:
        if candidate.id == container_id:
            container = candidate
            break
    if container is not None and container.title_element_id is not None:
        title = ir.elements.get(container.title_element_id)
        if title is not None:
            slide_title = _element_text(title)
    prefix = f"{container_id}/"
    for element in ir.elements.values():
        if not element.id.startswith(prefix):
            continue
        if element.id == figure.id or element.semantic_type in {"figure", "heading"}:
            continue
        text = _element_text(element)
        if text:
            nearby.append(text)
    return slide_title, nearby


def _element_text(element: Element) -> str | None:
    # Read plain visible text from one element
    text = element.content.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    return None


def _figure_labels(element: Element) -> list[str]:
    # Read or infer source labels for one diagram
    if element.subtype != "diagram":
        return []
    parsed: list[str] = []
    values = element.attrs.get("tikz_labels")
    if isinstance(values, list):
        for value in values:
            if isinstance(value, str):
                parsed.append(value)
    return infer_tikz_labels(element.source.raw or "", parsed)


__all__ = [
    "ADAPTER_REGISTRY",
    "PreparedDocument",
    "SourceAdapter",
    "WrittenDocument",
    "get_adapter",
]

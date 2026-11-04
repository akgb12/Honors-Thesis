from pathlib import Path

import pytest

from a11y_pipeline.adapters.tex_beamer.aux_reader import apply_aux_mapping, read_aux
from a11y_pipeline.adapters.tex_beamer.builder import build
from a11y_pipeline.adapters.tex_beamer.compile import compile_project
from a11y_pipeline.adapters.tex_beamer.markers import inject_markers
from a11y_pipeline.adapters.tex_beamer.parser import parse_file
from a11y_pipeline.adapters.tex_beamer.preflight import preflight
from a11y_pipeline.adapters.tex_beamer.working_copy import create_working_copies
from a11y_pipeline.bundle.bundle import Bundle
from a11y_pipeline.evaluation.concepts import infer_tikz_labels
from a11y_pipeline.evaluation.hidden_labels import detect_figure_hidden_labels

FIXTURES = Path(__file__).parents[1] / "fixtures"


@pytest.mark.tex
def test_lecture_page_seven_detects_hidden_fold_three(tmp_path: Path) -> None:
    # Prove rendered pixels hide the overdrawn Fold 3 label
    fixture = FIXTURES / "lecture_sample"
    bundle = Bundle.from_path(fixture)
    ir = build(parse_file(fixture), preflight(bundle))
    copies = create_working_copies(bundle, ir, tmp_path / "work")
    inject_markers(ir, copies.marked)
    original = compile_project(copies.original, bundle.main_file)
    marked = compile_project(copies.marked, bundle.main_file)
    mapped = apply_aux_mapping(ir, read_aux(marked.aux_path))
    figure = mapped.elements["slide_04/figure_01"]
    source = figure.content["source"]["raw"]
    labels = infer_tikz_labels(source, figure.attrs["tikz_labels"])

    assert figure.render.pages[-1] == 7
    assert figure.render.bbox is not None
    result = detect_figure_hidden_labels(original.pdf_path, figure, labels)

    measurements = []
    for word in result.words:
        if word.text == "3":
            measurements.append((word.text, word.bbox, word.luminance_stddev))
    assert result.hidden_labels == ["Fold 3"], measurements
    assert result.visible_labels == ["Fold 1", "Fold 2", "Fold 4", "Fold 5", "Test"]
    hidden_three = []
    for word in result.words:
        if word.text == "3" and word.hidden:
            hidden_three.append(word)
    assert len(hidden_three) == 1
    assert hidden_three[0].luminance_stddev is not None
    assert hidden_three[0].luminance_stddev < 20

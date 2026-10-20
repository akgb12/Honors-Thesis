from pathlib import Path

import pytest
from PIL import Image, ImageChops

from a11y_pipeline.adapters.tex_beamer.aux_reader import (
    apply_aux_mapping,
    read_aux,
)
from a11y_pipeline.adapters.tex_beamer.builder import build
from a11y_pipeline.adapters.tex_beamer.compile import CompileError, compile_project
from a11y_pipeline.adapters.tex_beamer.markers import inject_markers
from a11y_pipeline.adapters.tex_beamer.parser import parse_file
from a11y_pipeline.adapters.tex_beamer.preflight import preflight
from a11y_pipeline.adapters.tex_beamer.working_copy import create_working_copies
from a11y_pipeline.bundle.bundle import Bundle
from a11y_pipeline.render.crop import (
    crop_pdf_bbox,
    page_box_points,
    pdf_bbox_to_pixels,
)
from a11y_pipeline.render.pages import render_page, render_pages
from a11y_pipeline.render.pixeldiff import (
    compare_pdf_pixels,
    visual_change_issues,
)

FIXTURES = Path(__file__).parents[1] / "fixtures"


@pytest.mark.tex
def test_lecture_marker_compile_mapping_and_rendering(tmp_path: Path) -> None:
    # Verify the complete deterministic M5 lecture pipeline
    fixture = FIXTURES / "lecture_sample"
    bundle = Bundle.from_path(fixture)
    ir = build(parse_file(fixture), preflight(bundle))
    copies = create_working_copies(bundle, ir, tmp_path / "work")
    table_path = tmp_path / "injection_table.json"

    records = inject_markers(ir, copies.marked, table_path)
    marked_source = (copies.marked / bundle.main_file).read_text(encoding="utf-8")
    original_result = compile_project(copies.original, bundle.main_file)
    marked_result = compile_project(copies.marked, bundle.main_file)
    mapped = apply_aux_mapping(ir, read_aux(marked_result.aux_path))
    pixel_check = compare_pdf_pixels(original_result.pdf_path, marked_result.pdf_path)

    assert original_result.errors == 0
    assert marked_result.errors == 0
    assert original_result.page_count == 10
    assert marked_result.page_count == 10
    assert pixel_check.identical
    assert pixel_check.different_pages == []
    assert visual_change_issues(mapped, pixel_check) == []
    assert len(render_pages(original_result.pdf_path, tmp_path / "pages", dpi=110)) == 10
    assert table_path.is_file()

    ids: list[str] = []
    for record in records:
        ids.append(record.id)
    assert "slide_06/unknown_01" not in ids
    assert r"\myplot{results.csv}" in marked_source
    assert r"\aelspan{slide_06-unknown_01" not in marked_source
    assert (
        r"\title[Introduction to Machine Learning]"
        r"{\aelspan{slide_01-title_page_01-document_title_01}"
    ) in marked_source
    assert r"\[\aelspan{slide_03-formula_01}{2}{Formula}{" in marked_source
    assert r"\only<1>{\aelspan{slide_05-paragraph_01}{1}{P}{" in marked_source

    cv_figure = mapped.elements["slide_04/figure_01"]
    assert cv_figure.render.pages == [6, 7]
    assert cv_figure.render.bbox is not None
    _assert_figure_bbox_accuracy(
        original_result.pdf_path,
        cv_figure.render.bbox,
        tmp_path,
    )

    regression = mapped.elements["slide_03/figure_01"]
    assert regression.render.bbox is not None
    crop_path = crop_pdf_bbox(
        original_result.pdf_path,
        regression.render.pages[-1],
        regression.render.bbox,
        tmp_path / "crops" / "regression.png",
    )
    with Image.open(crop_path) as crop:
        assert crop.width > 0
        assert crop.height > 0
        assert crop.getbbox() is not None


def _assert_figure_bbox_accuracy(
    pdf_path: Path,
    bbox: tuple[float, float, float, float],
    output_root: Path,
) -> None:
    # Compare marker bounds with the visible overlay difference
    hidden_path = render_page(pdf_path, 6, output_root / "hidden.png", 100)
    visible_path = render_page(pdf_path, 7, output_root / "visible.png", 100)
    page_box = page_box_points(pdf_path, 7)
    with Image.open(hidden_path) as hidden_image:
        with Image.open(visible_path) as visible_image:
            hidden = hidden_image.convert("RGB")
            visible = visible_image.convert("RGB")
            predicted = pdf_bbox_to_pixels(bbox, page_box, 100, image_size=hidden.size)
            expanded = (
                max(0, predicted[0] - 5),
                max(0, predicted[1] - 5),
                min(hidden.width, predicted[2] + 5),
                min(hidden.height, predicted[3] + 5),
            )
            difference = ImageChops.difference(hidden, visible).crop(expanded)
            local_actual = difference.getbbox()
    assert local_actual is not None
    actual = (
        local_actual[0] + expanded[0],
        local_actual[1] + expanded[1],
        local_actual[2] + expanded[0],
        local_actual[3] + expanded[1],
    )
    for expected_value, actual_value in zip(predicted, actual, strict=True):
        assert abs(expected_value - actual_value) <= 2


@pytest.mark.tex
def test_compile_failure_reports_first_tex_error(tmp_path: Path) -> None:
    # Surface the first TeX error with its source line
    source = "\\documentclass{beamer}\n\\input{bad}\n\\begin{document}\n\\end{document}\n"
    (tmp_path / "main.tex").write_text(source, encoding="utf-8")
    (tmp_path / "bad.tex").write_text("\\undefinedcommand\n", encoding="utf-8")

    with pytest.raises(CompileError) as caught:
        compile_project(tmp_path, "main.tex")

    assert caught.value.source_file == "bad.tex"
    assert caught.value.line == 1
    assert caught.value.tex_error is not None
    assert "Undefined control sequence" in caught.value.tex_error
    assert caught.value.log_path.is_file()

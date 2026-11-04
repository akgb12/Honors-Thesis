import shutil
from pathlib import Path

from a11y_pipeline.adapters.tex_beamer.aux_reader import (
    apply_aux_mapping,
    parse_aux,
)
from a11y_pipeline.adapters.tex_beamer.builder import build
from a11y_pipeline.adapters.tex_beamer.markers import inject_markers
from a11y_pipeline.adapters.tex_beamer.parser import parse_file
from a11y_pipeline.adapters.tex_beamer.preflight import preflight
from a11y_pipeline.adapters.tex_beamer.working_copy import create_working_copies
from a11y_pipeline.bundle.bundle import Bundle
from a11y_pipeline.render.crop import pdf_bbox_to_pixels

FIXTURES = Path(__file__).parents[1] / "fixtures"


def test_working_copies_replace_missing_image_from_ir_span(tmp_path: Path) -> None:
    # Preserve fixtures while replacing only the copied image command
    source = FIXTURES / "lecture_sample"
    project = tmp_path / "input"
    shutil.copytree(source, project)
    (project / "figs" / "regression.png").unlink()
    original_source = (project / "main.tex").read_text(encoding="utf-8")
    bundle = Bundle.from_path(project)
    ir = build(parse_file(project), preflight(bundle))

    copies = create_working_copies(bundle, ir, tmp_path / "work")
    expected = (
        r"\fbox{\parbox[c][3cm][c]{0.45\textwidth}"
        r"{\centering\small missing: \texttt{figs/regression}}}"
    )

    assert expected in (copies.original / "main.tex").read_text(encoding="utf-8")
    assert expected in (copies.marked / "main.tex").read_text(encoding="utf-8")
    assert (project / "main.tex").read_text(encoding="utf-8") == original_source


def test_marker_injection_skips_fragile_frames(tmp_path: Path) -> None:
    # Leave fragile content untouched and report the frame
    project = tmp_path / "input"
    project.mkdir()
    source = (
        "\\documentclass{beamer}\n"
        "\\begin{document}\n"
        "\\begin{frame}[fragile]{Code}\n"
        "\\begin{verbatim}\n"
        "\\item literal\n"
        "\\end{verbatim}\n"
        "\\end{frame}\n"
        "\\end{document}\n"
    )
    (project / "main.tex").write_text(source, encoding="utf-8")
    bundle = Bundle.from_path(project)
    ir = build(parse_file(project))
    copies = create_working_copies(bundle, ir, tmp_path / "work")

    records = inject_markers(ir, copies.marked)
    marked = (copies.marked / "main.tex").read_text(encoding="utf-8")

    assert records == []
    assert r"\aelspan{slide_01" not in marked
    assert r"\begin{verbatim}" in marked
    assert ir.issues[-1].code == "unmarked_fragile"


def test_aux_mapping_uses_scaled_points_and_last_figure_page() -> None:
    # Map repeated figure records with bottom left PDF coordinates
    source = (
        "\\documentclass{beamer}\n"
        "\\begin{document}\n"
        "\\begin{frame}{Figure}\n"
        "\\begin{tikzpicture}\\node{A};\\end{tikzpicture}\n"
        "\\end{frame}\n"
        "\\end{document}\n"
    )
    ir = build(parse_file_source(source))
    heading = ir.elements["slide_01/heading_01"]
    figure = ir.elements["slide_01/figure_01"]
    heading.mcid = 0
    figure.mcid = 1
    aux = (
        "\\aelspanpos{slide_01-heading_01}{1}\n"
        "\\zref@newlabel{slide_01-heading_01@1}{\\posx{65536}\\posy{131072}}\n"
        "\\aelsize{slide_01-figure_01}{10pt}{4pt}{1pt}{1}\n"
        "\\aelsize{slide_01-figure_01}{10pt}{4pt}{1pt}{2}\n"
        "\\zref@newlabel{slide_01-figure_01@1}{\\posx{655360}\\posy{1310720}}\n"
        "\\zref@newlabel{slide_01-figure_01@2}{\\posx{1310720}\\posy{1966080}}\n"
    )

    mapped = apply_aux_mapping(ir, parse_aux(aux))
    mapped_figure = mapped.elements[figure.id]

    assert mapped.elements[heading.id].render.anchor == (1.0, 2.0)
    assert mapped_figure.render.pages == [1, 2]
    assert mapped_figure.render.anchor == (20.0, 30.0)
    assert mapped_figure.render.bbox == (20.0, 29.0, 30.0, 34.0)
    assert mapped_figure.render.confidence == 0.95
    assert mapped.containers[0].rendered_pages == [1, 2]


def parse_file_source(source: str):
    # Parse an inline source through the public parser
    from a11y_pipeline.adapters.tex_beamer.parser import parse

    return parse(source)


def test_pdf_bbox_conversion_flips_vertical_coordinates() -> None:
    # Convert point bounds into a top left pixel rectangle
    converted = pdf_bbox_to_pixels(
        (72.0, 144.0, 216.0, 216.0),
        (0.0, 0.0, 612.0, 792.0),
        100,
        padding=4,
    )

    assert converted == (96, 796, 304, 904)

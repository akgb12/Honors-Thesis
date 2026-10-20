from pathlib import Path

import pikepdf

from a11y_pipeline.evaluation.pdf_checks import check_pdf
from a11y_pipeline.ir.ids import fingerprint_source
from a11y_pipeline.ir.models import (
    Accessibility,
    Container,
    DocumentIR,
    Element,
    Fidelity,
    RenderRef,
    SourceRef,
)
from a11y_pipeline.synthesis.plan import OutputOperation
from a11y_pipeline.synthesis.tagger import tag_pdf


def test_tagger_uses_exact_formula_tex_and_reports_failed_figure(tmp_path: Path) -> None:
    # Set formula text while leaving failed figure alt absent
    marked = tmp_path / "marked.pdf"
    output = tmp_path / "tagged.pdf"
    _write_two_marker_pdf(marked)
    ir = _formula_and_failed_figure_ir()

    result = tag_pdf(marked, ir, output)
    checked = check_pdf(output, ir)
    codes: list[str] = []
    for issue in result.issues:
        codes.append(issue.code)

    assert codes == ["alt_missing"]
    assert checked.passed
    with pikepdf.open(output) as pdf:
        section = pdf.Root.StructTreeRoot.K.K[0]
        formula = section.K[0]
        figure = section.K[1]
        assert str(formula.Alt) == r"\frac{a}{b}"
        assert formula.get("/Alt") is not None
        assert figure.get("/Alt") is None


def test_output_operation_is_strict_serializable_record() -> None:
    # Store one report ready output operation
    operation = OutputOperation(
        output="tagged_pdf",
        operation="artifact_overlay",
        element_id="slide_01/paragraph_01",
        page=1,
        details={"mcid": 0},
    )

    assert operation.model_dump() == {
        "output": "tagged_pdf",
        "operation": "artifact_overlay",
        "element_id": "slide_01/paragraph_01",
        "source_file": None,
        "page": 1,
        "details": {"mcid": 0},
    }


def _write_two_marker_pdf(path: Path) -> None:
    # Write one page containing two semantic markers
    pdf = pikepdf.new()
    page = pdf.add_blank_page(page_size=(200, 200))
    content = b"/Formula <</MCID 0>> BDC q Q EMC\n/Figure <</MCID 1>> BDC q Q EMC\n"
    page.obj.Contents = pdf.make_stream(content)
    pdf.save(path)


def _formula_and_failed_figure_ir() -> DocumentIR:
    # Build mapped formula and failed figure elements
    formula_raw = r"\[\frac{a}{b}\]"
    formula = Element(
        id="slide_01/formula_01",
        semantic_type="formula",
        parent_id="slide_01",
        content={"tex": r"\frac{a}{b}", "inline": False},
        fingerprint=fingerprint_source(formula_raw),
        source=SourceRef(
            file="main.tex",
            line_start=1,
            line_end=1,
            char_start=0,
            char_end=len(formula_raw),
            native_type="display math",
            raw=formula_raw,
        ),
        render=RenderRef(pages=[1], mapping_method="marker", confidence=0.8),
        accessibility=Accessibility(role="Formula"),
        fidelity=Fidelity(signature=r"\frac{a}{b}"),
        mcid=0,
    )
    figure_raw = r"\includegraphics{missing}"
    figure = Element(
        id="slide_01/figure_01",
        semantic_type="figure",
        subtype="image",
        parent_id="slide_01",
        content={"asset_id": "asset_01"},
        fingerprint=fingerprint_source(figure_raw),
        source=SourceRef(
            file="main.tex",
            line_start=2,
            line_end=2,
            char_start=len(formula_raw) + 1,
            char_end=len(formula_raw) + 1 + len(figure_raw),
            native_type="includegraphics",
            raw=figure_raw,
        ),
        render=RenderRef(pages=[1], mapping_method="marker", confidence=0.95),
        accessibility=Accessibility(role="Figure", status="failed"),
        mcid=1,
    )
    elements = {formula.id: formula, figure.id: figure}
    return DocumentIR(
        document_id="synthesis1234567",
        source_format="tex-beamer",
        main_file="main.tex",
        metadata={"title": "Synthesis fixture", "lang": "en-US"},
        containers=[
            Container(
                id="slide_01",
                kind="slide",
                element_ids=[formula.id, figure.id],
                rendered_pages=[1],
            )
        ],
        elements=elements,
    )

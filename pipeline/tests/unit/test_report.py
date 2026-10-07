from pathlib import Path

import pikepdf
from PIL import Image

from a11y_pipeline.evaluation.pdf_checks import PdfCheckResult
from a11y_pipeline.ir.ids import fingerprint_source
from a11y_pipeline.ir.models import (
    Accessibility,
    Candidate,
    Container,
    DocumentIR,
    Element,
    Issue,
    RenderRef,
    SourceRef,
)
from a11y_pipeline.render.pixeldiff import PixelCheck
from a11y_pipeline.report.html import write_html_report
from a11y_pipeline.report.stats import build_report_stats


def test_report_contains_summary_pages_issues_elements_and_history(tmp_path: Path) -> None:
    # Render all required M12 report sections
    ir = _document()
    candidate = Candidate(
        candidate_id="c1",
        round=0,
        patches=[],
        scores={"A": 80.0, "F": 100.0},
    )
    issue = Issue(
        element_id="slide_01/unknown_01",
        code="not_handled",
        severity="warning",
        message="Unknown source command",
    )
    telemetry = tmp_path / "telemetry.jsonl"
    telemetry.write_text(
        '{"cost_usd":0.0,"input_tokens":12,"output_tokens":8,"status":"ok"}\n',
        encoding="utf-8",
    )
    checks = PdfCheckResult(
        checks={
            "structure_completeness": True,
            "language": True,
            "info_title": True,
            "xmp_title": True,
            "display_document_title": True,
        },
        issues=[],
        pages=[],
    )
    stats = build_report_stats(
        ir,
        candidate,
        telemetry,
        "nothing_failing",
        pdf_checks=checks,
        pixel_check=PixelCheck(True, 1, 1, []),
        text_similarity=100.0,
        issues=[issue],
    )
    pdf_path = tmp_path / "output" / "tagged.pdf"
    pdf_path.parent.mkdir()
    _write_blank_pdf(pdf_path)
    image_path = tmp_path / "pages" / "page-1.png"
    image_path.parent.mkdir()
    Image.new("RGB", (400, 300), "white").save(image_path)

    report = write_html_report(
        tmp_path / "report.html",
        tmp_path,
        ir,
        [candidate],
        "c1",
        [issue],
        stats,
        [image_path],
        pdf_path,
    )

    html = report.read_text(encoding="utf-8")
    assert "Preliminary A" in html
    assert "Preliminary F" in html
    assert "Input tokens" in html
    assert "nothing_failing" in html
    assert "page-1.png" in html
    assert "element-box status-model_generated" in html
    assert "Unknown source command" in html
    assert "slide_01/figure_01" in html
    assert "Candidate round history" in html
    assert "Not handled" in html
    assert stats.input_tokens == 12
    assert stats.output_tokens == 8
    assert stats.accessibility.applicable_metrics["I"] == 80.0


def _document() -> DocumentIR:
    # Build a mapped report fixture
    figure = _element(
        "slide_01/figure_01",
        "figure",
        "Figure",
        "model_generated",
        2,
        RenderRef(
            pages=[1],
            bbox=(20.0, 30.0, 100.0, 120.0),
            mapping_method="marker",
            confidence=0.95,
        ),
    )
    figure.subtype = "diagram"
    figure.accessibility.alt_text = "Five folds with one test fold"
    unknown = _element(
        "slide_01/unknown_01",
        "unknown",
        "",
        "not_handled",
        3,
        RenderRef(),
    )
    return DocumentIR(
        document_id="reportfixture12",
        source_format="tex-beamer",
        main_file="main.tex",
        metadata={"title": "Report fixture", "lang": "en-US"},
        containers=[
            Container(
                id="slide_01",
                kind="slide",
                element_ids=[figure.id, unknown.id],
                rendered_pages=[1],
            )
        ],
        elements={figure.id: figure, unknown.id: unknown},
    )


def _element(
    element_id: str,
    semantic_type: str,
    role: str,
    status: str,
    line: int,
    render: RenderRef,
) -> Element:
    # Build one report element
    raw = element_id
    return Element(
        id=element_id,
        semantic_type=semantic_type,
        parent_id="slide_01",
        fingerprint=fingerprint_source(raw),
        source=SourceRef(
            file="main.tex",
            line_start=line,
            line_end=line,
            char_start=line * 10,
            char_end=line * 10 + len(raw),
            native_type=semantic_type,
            raw=raw,
        ),
        render=render,
        accessibility=Accessibility(role=role or None, status=status),
    )


def _write_blank_pdf(path: Path) -> None:
    # Write one page with Beamer sized media bounds
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(362.835, 272.126))
    pdf.save(path)

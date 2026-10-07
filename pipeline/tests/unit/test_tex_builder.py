from pathlib import Path

from a11y_pipeline.adapters.tex_beamer.builder import build, summarize
from a11y_pipeline.adapters.tex_beamer.parser import parse_file
from a11y_pipeline.adapters.tex_beamer.preflight import preflight
from a11y_pipeline.bundle.bundle import Bundle

FIXTURES = Path(__file__).parents[1] / "fixtures"


def _golden(path: Path) -> str:
    # Read golden content without its documentation lines
    included: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            continue
        if not line:
            continue
        included.append(line)
    return "\n".join(included) + "\n"


def test_adversarial_summary_matches_exact_golden() -> None:
    # Match the documented adversarial IR summary exactly
    fixture = FIXTURES / "adversarial"
    ir = build(parse_file(fixture))

    assert summarize(ir) == _golden(fixture / "expected_elements.txt")


def test_builder_preserves_hierarchy_metadata_and_formula_signatures() -> None:
    # Verify canonical hierarchy and source fidelity
    fixture = FIXTURES / "lecture_sample"
    bundle = Bundle.from_path(fixture)
    ir = build(parse_file(fixture), preflight(bundle))

    assert ir.main_file == "main.tex"
    assert ir.metadata == {
        "title": "Introduction to Machine Learning",
        "subtitle": "Lecture 1",
        "author": "Dr. Example",
        "institute": "Texas A&M University",
        "date": "Fall 2026",
        "lang": "en-US",
    }
    title_page = ir.elements["slide_01/title_page_01"]
    assert title_page.child_ids == [
        "slide_01/title_page_01/document_title_01",
        "slide_01/title_page_01/paragraph_01",
        "slide_01/title_page_01/paragraph_02",
        "slide_01/title_page_01/paragraph_03",
        "slide_01/title_page_01/paragraph_04",
    ]
    paragraph = ir.elements["slide_03/paragraph_01"]
    assert paragraph.child_ids == ["slide_03/paragraph_01/formula_01"]
    inline_formula = ir.elements[paragraph.child_ids[0]]
    display_formula = ir.elements["slide_03/formula_01"]
    assert inline_formula.fidelity.signature == r"\hat{y} = w^\top x + b"
    assert display_formula.fidelity.signature == (
        r"L(w) = \frac{1}{n}\sum_{i=1}^{n} \left(y_i - w^\top x_i\right)^2"
    )


def test_builder_maps_preflight_assets_figures_and_unknowns() -> None:
    # Verify figure states assets labels and unsupported issues
    fixture = FIXTURES / "lecture_sample"
    bundle = Bundle.from_path(fixture)
    ir = build(parse_file(fixture), preflight(bundle))

    image = ir.elements["slide_03/figure_01"]
    image_asset = ir.assets[image.content["asset_id"]]
    assert image.subtype == "image"
    assert image.accessibility.status == "needs_description"
    assert image_asset.referenced_as == "figs/regression"
    assert image_asset.resolved_path == "figs/regression.png"
    assert image_asset.used_by == [image.id]

    diagram = ir.elements["slide_04/figure_01"]
    assert diagram.subtype == "diagram"
    assert diagram.attrs["tikz_labels"] == [r"Fold \n", "Test"]
    assert diagram.content["source"]["raw"].startswith(r"\begin{tikzpicture}")
    assert diagram.accessibility.status == "needs_description"

    unknown = ir.elements["slide_06/unknown_01"]
    assert unknown.accessibility.status == "not_handled"
    assert unknown.attrs["args"] == ["results.csv"]
    assert ir.issues[-1].element_id == unknown.id
    assert ir.issues[-1].code == "not_handled"


def test_builder_marks_absent_images_and_keeps_stable_fingerprints() -> None:
    # Verify parser only builds remain deterministic
    fixture = FIXTURES / "adversarial"
    first = build(parse_file(fixture))
    second = build(parse_file(fixture))

    figure = first.elements["slide_03/figure_01"]
    asset = first.assets[figure.content["asset_id"]]
    assert figure.accessibility.status == "missing_asset"
    assert asset.status == "missing"
    assert first.document_id == second.document_id
    assert figure.fingerprint == second.elements[figure.id].fingerprint
    assert len(figure.fingerprint) == 16

from a11y_pipeline.evaluation.concepts import _clean_tikz_label, evaluate_coverage
from a11y_pipeline.evaluation.vetoes import figure_contradiction_veto
from a11y_pipeline.ir.ids import fingerprint_source
from a11y_pipeline.ir.models import Accessibility, Element, Fidelity, SourceRef


def _figure(alt_text: str, required: list[str], excluded: list[str] | None = None) -> Element:
    # Build one diagram figure with alt text and label concepts
    raw = "tikz"
    return Element(
        id="slide_09/figure_01",
        semantic_type="figure",
        subtype="diagram",
        parent_id="slide_09",
        content={},
        fingerprint=fingerprint_source(raw),
        source=SourceRef(
            file="main.tex",
            line_start=1,
            line_end=2,
            char_start=0,
            char_end=len(raw),
            native_type="tikzpicture",
            raw=raw,
        ),
        accessibility=Accessibility(role="Figure", status="model_generated", alt_text=alt_text),
        fidelity=Fidelity(required_concepts=required, excluded_concepts=excluded or []),
    )


def test_tikz_line_breaks_are_removed_from_labels() -> None:
    # A TeX line break inside a node label becomes a space
    assert _clean_tikz_label(r"Input\\ e.g., image") == "Input e.g., image"
    assert _clean_tikz_label(r"Two\\[2pt]lines") == "Two lines"
    assert _clean_tikz_label(r"A\ B") == "A B"


def test_punctuation_differences_do_not_break_label_coverage() -> None:
    # "Input, e.g., image" covers the label "Input e.g., image"
    alt = "Flow diagram: 'Input, e.g., image' leads to 'Write a program'."
    coverage = evaluate_coverage(alt, ["label:Input e.g., image", "label:Write a program"])
    assert coverage.coverage == 1.0


def test_quote_with_different_punctuation_is_not_a_contradiction() -> None:
    # The same words with different punctuation or a stray TeX backslash are the same label
    element = _figure('Boxes: "Input, e.g., image" and "Write a program".', [])
    visible = ["Input\\ e.g., image", "Write a program"]
    assert figure_contradiction_veto(element, visible) is None


def test_quote_of_a_label_that_is_not_in_the_figure_is_still_vetoed() -> None:
    # A made-up label is still a contradiction
    element = _figure('Boxes: "Output, e.g., dog".', [])
    veto = figure_contradiction_veto(element, ["Input e.g., image", "Write a program"])
    assert veto is not None
    assert veto.details["quoted_label"] == "Output, e.g., dog"


def test_quote_is_not_vetoed_when_no_labels_could_be_extracted() -> None:
    # With nothing to compare against, the quote cannot be called wrong
    element = _figure('A bar labeled "Average test loss = Loss_1".', [])
    assert figure_contradiction_veto(element, []) is None


def test_quote_of_a_hidden_label_is_still_vetoed() -> None:
    # A label known to be hidden stays vetoed even though no label is visible
    element = _figure('The third box is labeled "Fold 3".', [], excluded=["label:Fold 3"])
    veto = figure_contradiction_veto(element, [])
    assert veto is not None
    assert veto.details["quoted_label"] == "Fold 3"

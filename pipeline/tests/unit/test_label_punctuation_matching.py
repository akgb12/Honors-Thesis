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


def test_prose_sentences_inside_a_figure_are_not_required_labels() -> None:
    # A sentence drawn in a TikZ node is prose, so alt text need not repeat it word for word
    from a11y_pipeline.evaluation.concepts import build_figure_concepts

    figure = _figure("", [])
    sentence = "Description: red points lie mostly below the line; blue points lie above it."
    concepts = build_figure_concepts(figure, [], ["Input", "Write a program", sentence], [])

    assert concepts.required == ["label:Input", "label:Write a program"]
    assert sentence in concepts.visible_labels


def test_prompt_states_the_same_alt_text_budget_the_checker_enforces() -> None:
    # The model must be told the word budget that the length signal applies
    from pathlib import Path

    import a11y_pipeline.capabilities as capabilities
    from a11y_pipeline.capabilities.figure_description import PROMPT_VERSION
    from a11y_pipeline.evaluation.signals import ALT_BASE_WORD_LIMIT

    prompt = (Path(capabilities.__file__).parent / "prompts" / f"{PROMPT_VERSION}.md").read_text()
    assert f"at most {ALT_BASE_WORD_LIMIT} words" in prompt
    assert "extended_description" in prompt


def test_coverage_counts_the_extended_description_that_screen_readers_receive() -> None:
    # The tagged PDF delivers alt text plus the extended description, so both are scored
    from a11y_pipeline.evaluation.concepts import delivered_description, evaluate_coverage

    figure = _figure("Flow from input to output.", ["label:New input e.g., image"])
    figure.accessibility.extended_description = (
        "Bottom row: New input (e.g., image) leads to Output."
    )

    assert delivered_description(figure) == (
        "Flow from input to output.\n\nBottom row: New input (e.g., image) leads to Output."
    )
    assert (
        evaluate_coverage(delivered_description(figure), figure.fidelity.required_concepts).coverage
        == 1.0
    )
    assert (
        evaluate_coverage(figure.accessibility.alt_text, figure.fidelity.required_concepts).coverage
        == 0.0
    )


def test_a_made_up_label_in_the_extended_description_is_vetoed() -> None:
    # Unverifiable quotes are contradictions wherever the screen reader would read them
    figure = _figure("A flow diagram.", [])
    figure.accessibility.extended_description = 'The last box is labeled "Profit margin".'
    veto = figure_contradiction_veto(figure, ["Input", "Output"])
    assert veto is not None
    assert veto.details["quoted_label"] == "Profit margin"


def test_partial_count_in_the_extended_description_is_not_a_contradiction() -> None:
    # "The remaining four folds" is correct for five folds with one held out
    figure = _figure(
        "Five-fold cross-validation with the third fold held out.", ["sequence:5:Fold"]
    )
    figure.accessibility.extended_description = "The remaining four folds are training folds."
    assert (
        figure_contradiction_veto(figure, ["Fold 1", "Fold 2", "Fold 4", "Fold 5", "Test"]) is None
    )


def test_quoting_part_of_a_real_label_is_not_a_contradiction() -> None:
    # "Output" refers to the visible label "Output e.g., cat/dog"
    element = _figure("A flow diagram.", [])
    element.accessibility.extended_description = "An arrow points to 'Output' and then to 'Write'."
    visible = ["Output e.g., cat/dog", "Write a program"]
    assert figure_contradiction_veto(element, visible) is None


def test_partial_words_and_invented_labels_are_still_vetoed() -> None:
    # Only whole words of a real label count, and invented labels remain contradictions
    visible = ["Output e.g., cat/dog", "Write a program"]
    partial = _figure('The box "Out" is shown.', [])
    assert figure_contradiction_veto(partial, visible) is not None
    invented = _figure('The box "Profit margin" is shown.', [])
    assert figure_contradiction_veto(invented, visible) is not None

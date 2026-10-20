import pytest

from a11y_pipeline.evaluation.concepts import (
    apply_concepts,
    build_figure_concepts,
    concept_matches,
    evaluate_coverage,
    infer_tikz_labels,
)
from a11y_pipeline.evaluation.scores import (
    compute_preliminary_scores,
    figure_accessibility_score,
)
from a11y_pipeline.evaluation.signals import evaluate_signals
from a11y_pipeline.evaluation.vetoes import (
    evaluate_vetoes,
    figure_contradiction_veto,
)
from a11y_pipeline.ir.ids import fingerprint_source
from a11y_pipeline.ir.models import (
    Accessibility,
    Container,
    DocumentIR,
    Element,
    Fidelity,
    Issue,
    SourceRef,
)

LECTURE_TIKZ = r"""
\begin{tikzpicture}
  \foreach \i in {0,...,4}{
    \pgfmathtruncatemacro{\n}{\i+1}
    \node at (\i,0) {\small Fold \n};
  }
  \node at (2,0) {\small Test};
\end{tikzpicture}
"""


def _figure(subtype: str = "diagram") -> Element:
    # Build one figure for evaluation tests
    content: dict[str, object] = {}
    attrs: dict[str, object] = {}
    raw = "figure.png"
    if subtype == "diagram":
        raw = LECTURE_TIKZ
        content["source"] = {"raw": raw}
        attrs["tikz_labels"] = [r"Fold \n", "Test"]
    else:
        content["asset_id"] = "asset_01"
    return Element(
        id="slide_04/figure_01",
        semantic_type="figure",
        subtype=subtype,
        parent_id="slide_04",
        content=content,
        attrs=attrs,
        fingerprint=fingerprint_source(raw),
        source=SourceRef(
            file="main.tex",
            line_start=1,
            line_end=8,
            char_start=0,
            char_end=len(raw),
            native_type="tikzpicture" if subtype == "diagram" else "includegraphics",
            raw=raw,
        ),
        accessibility=Accessibility(role="Figure", status="model_generated"),
    )


def _formula_document(signature: str) -> DocumentIR:
    # Build one formula document with an exact source signature
    raw = r"\[x+1\]"
    element = Element(
        id="slide_01/formula_01",
        semantic_type="formula",
        parent_id="slide_01",
        content={"tex": signature, "inline": False},
        fingerprint=fingerprint_source(raw),
        source=SourceRef(
            file="main.tex",
            line_start=1,
            line_end=1,
            char_start=0,
            char_end=len(raw),
            native_type="display_math",
            raw=raw,
        ),
        accessibility=Accessibility(role="Formula"),
        fidelity=Fidelity(signature=signature),
    )
    return DocumentIR(
        document_id="formula123456789",
        source_format="tex-beamer",
        main_file="main.tex",
        containers=[
            Container(
                id="slide_01",
                kind="slide",
                element_ids=[element.id],
            )
        ],
        elements={element.id: element},
    )


def test_foreach_labels_and_hidden_replacement_build_sequence() -> None:
    # Infer lecture labels and replace numbered labels with one sequence
    labels = infer_tikz_labels(LECTURE_TIKZ, [r"Fold \n", "Test"])
    assert labels == ["Fold 1", "Fold 2", "Fold 3", "Fold 4", "Fold 5", "Test"]

    concepts = build_figure_concepts(
        _figure(),
        nearby_text=["One fold is used for testing; the others are used for training."],
        visible_labels=labels,
        hidden_labels=["Fold 3"],
    )

    assert concepts.required == ["sequence:5:Fold", "label:Test"]
    assert concepts.excluded == ["label:Fold 3"]
    assert concepts.visible_labels == ["Fold 1", "Fold 2", "Fold 4", "Fold 5", "Test"]
    updated = apply_concepts(_figure(), concepts)
    assert updated.fidelity.required_concepts == concepts.required


def test_nearby_text_moves_matching_concepts_to_exclusions() -> None:
    # Exclude concepts already stated in nearby text
    concepts = build_figure_concepts(
        _figure(),
        nearby_text=["The diagram labels five folds and marks Test."],
        visible_labels=["Fold 1", "Fold 2", "Fold 4", "Fold 5", "Test"],
        hidden_labels=["Fold 3"],
    )

    assert concepts.required == []
    assert concepts.excluded == [
        "label:Fold 3",
        "sequence:5:Fold",
        "label:Test",
    ]


def test_weak_good_and_number_word_coverage() -> None:
    # Distinguish weak and complete cross validation descriptions
    required = ["sequence:5:Fold", "label:Test"]
    weak = evaluate_coverage("Five boxes in a row, one is blue.", required)
    good = evaluate_coverage(
        "Five-fold cross-validation: a row of five folds where the third position "
        "is the test fold.",
        required,
    )

    assert weak.coverage == 0.0
    assert weak.missing == required
    assert good.coverage == 1.0
    assert good.matched == required
    assert concept_matches("Twenty folds", "sequence:20:fold")
    assert concept_matches("0 boxes", "count:0:box")
    assert not concept_matches("twenty-one folds", "sequence:20:fold")


def test_raster_coverage_is_unavailable() -> None:
    # Mark raster source concept coverage as unavailable
    concepts = build_figure_concepts(
        _figure("image"),
        nearby_text=["Regression results"],
    )
    coverage = evaluate_coverage("A fitted line follows the observations.", concepts.required)

    assert concepts.required == []
    assert coverage.coverage is None
    assert not coverage.applicable
    assert concepts.issues[0].code == "coverage_unavailable"
    assert concepts.issues[0].severity == "info"


def test_signal_flags_cover_presence_filename_opener_duplicate_and_length() -> None:
    # Flag each deterministic description quality signal
    missing = evaluate_signals("figure", None, [], [])
    filename = evaluate_signals("figure", "figs/chart.png", [], [])
    opener = evaluate_signals("figure", "Image of five folds.", ["sequence:5:Fold"], [])
    duplicate = evaluate_signals(
        "figure",
        "Five folds with one test fold",
        ["sequence:5:Fold"],
        ["Five folds with one test fold"],
    )
    long_text = "word " * 81
    length = evaluate_signals("figure", long_text, ["label:Test"], [])

    assert missing.flags == ["alt_missing"]
    assert filename.flags == ["alt_file_name"]
    assert opener.flags == ["alt_forbidden_opener"]
    assert duplicate.flags == ["alt_near_duplicate"]
    assert length.flags == ["alt_length_outlier"]
    assert length.word_count == 81
    assert length.length_limit == 80


def test_wrong_count_and_unknown_quoted_label_are_vetoed() -> None:
    # Veto supported source contradictions
    element = _figure()
    element.fidelity = Fidelity(required_concepts=["sequence:5:Fold", "label:Test"])
    element.accessibility.alt_text = "Four folds with the third marked Test."
    count_issue = figure_contradiction_veto(
        element,
        ["Fold 1", "Fold 2", "Fold 4", "Fold 5", "Test"],
    )

    assert count_issue is not None
    assert count_issue.code == "contradicts_source"
    assert count_issue.details["expected"] == 5
    assert count_issue.details["stated"] == 4

    element.accessibility.alt_text = 'Five folds with the third marked "Validation".'
    label_issue = figure_contradiction_veto(
        element,
        ["Fold 1", "Fold 2", "Fold 4", "Fold 5", "Test"],
    )
    assert label_issue is not None
    assert label_issue.details["quoted_label"] == "Validation"


def test_formula_structure_and_visual_vetoes_are_collected() -> None:
    # Collect formula structure and visual veto classes
    source = _formula_document("x+1")
    candidate = _formula_document("x-1")
    structure = Issue(
        element_id="slide_01/formula_01",
        code="structure_content_missing",
        severity="veto",
        message="Visible content is missing",
    )
    visual = Issue(
        element_id=None,
        code="visual_change",
        severity="veto",
        message="Page appearance changed",
    )

    vetoes = evaluate_vetoes(
        source,
        candidate,
        pdf_issues=[structure],
        visual_issues=[visual],
    )
    codes: list[str] = []
    for issue in vetoes:
        codes.append(issue.code)

    assert codes == ["formula_changed", "structure_content_missing", "visual_change"]


def test_score_indices_renormalize_without_combined_q() -> None:
    # Renormalize separate preliminary indices over applicable metrics
    report = compute_preliminary_scores(
        {"T": 100.0, "R": 50.0, "B": None},
        {"X": 80.0, "E": None, "O": 100.0},
    )

    assert report.accessibility.value == pytest.approx((0.18 * 100.0 + 0.15 * 50.0) / 0.33)
    assert report.fidelity.value == pytest.approx((0.25 * 80.0 + 0.05 * 100.0) / 0.30)
    assert report.accessibility.applicable_metrics == {"T": 100.0, "R": 50.0}
    assert report.fidelity.applicable_metrics == {"X": 80.0, "O": 100.0}
    assert report.candidate_scores() == {
        "A": report.accessibility.value,
        "F": report.fidelity.value,
    }
    assert "Q" not in report.candidate_scores()


def test_figure_score_handles_coverage_warnings_raster_and_vetoes() -> None:
    # Apply the provisional figure scoring branches
    assert figure_accessibility_score(True, 1.0, 0) == 100.0
    assert figure_accessibility_score(True, 0.5, 1) == 30.0
    assert figure_accessibility_score(True, None, 0) == 60.0
    assert figure_accessibility_score(True, None, 1) == 0.0
    assert figure_accessibility_score(True, 1.0, 0, vetoed=True) == 0.0
    assert figure_accessibility_score(True, 1.0, 0, missing_asset=True) == 0.0

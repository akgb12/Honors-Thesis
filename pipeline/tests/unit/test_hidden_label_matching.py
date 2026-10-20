from a11y_pipeline.evaluation.hidden_labels import WordBox, _matching_word_runs


def _words(*texts: str) -> list[WordBox]:
    # Build extracted words in reading order, one per line
    return [
        WordBox(text=text, bbox=(0.0, index * 10.0, 40.0, index * 10.0 + 9.0))
        for index, text in enumerate(texts)
    ]


def _texts(runs: list[list[WordBox]]) -> list[list[str]]:
    # Reduce runs to their word text for readable assertions
    return [[word.text for word in run] for run in runs]


def test_label_matches_words_on_one_line() -> None:
    # A plain label matches its own words
    runs = _matching_word_runs("Higher productivity", _words("Higher", "productivity", "Other"))
    assert _texts(runs) == [["Higher", "productivity"]]


def test_label_matches_a_word_hyphenated_across_lines() -> None:
    # LaTeX breaks "manpower" as "man-" / "power" inside a narrow box
    words = _words("Less", "man-", "power", "required", "Loss")
    assert _texts(_matching_word_runs("Less manpower required", words)) == [
        ["Less", "man-", "power", "required"]
    ]


def test_label_matches_text_wrapped_onto_several_lines() -> None:
    # A long label wrapped over lines still matches as one label
    words = _words("Loss", "of", "traditional", "jobs")
    assert _texts(_matching_word_runs("Loss of traditional jobs", words)) == [
        ["Loss", "of", "traditional", "jobs"]
    ]


def test_hyphenated_source_label_matches_its_extracted_word() -> None:
    # A label that contains a real hyphen matches the single extracted word
    words = _words("Self-attention", "layer")
    assert _texts(_matching_word_runs("Self-attention layer", words)) == [
        ["Self-attention", "layer"]
    ]


def test_label_ignores_case_and_punctuation() -> None:
    # Case and punctuation never decide visibility
    words = _words("NEW", "technology:")
    assert len(_matching_word_runs("New technology", words)) == 1


def test_partial_or_missing_labels_do_not_match() -> None:
    # A label only matches when every part of it is present
    assert _matching_word_runs("Less manpower required", _words("Less", "required")) == []
    assert _matching_word_runs("Fold 3", _words("Fold", "4")) == []
    assert _matching_word_runs("", _words("Fold")) == []

from a11y_pipeline.adapters.tex_beamer.parser import parse
from a11y_pipeline.adapters.tex_beamer.records import NativeRecord


def _records_of_kind(records: list[NativeRecord], kind: str) -> list[NativeRecord]:
    # Gather matching native records recursively
    matches: list[NativeRecord] = []
    for record in records:
        if record.kind == kind:
            matches.append(record)
        matches.extend(_records_of_kind(record.children, kind))
    return matches


def _only_record(records: list[NativeRecord], kind: str) -> NativeRecord:
    # Return the sole record of one kind
    matches = _records_of_kind(records, kind)
    assert len(matches) == 1
    return matches[0]


def test_frame_prefix_peels_overlay_options_and_title() -> None:
    # Peel Beamer prefixes that arrive as character and group children
    source = "\\begin{frame}<2->[fragile,label=x]{A Title}\nBody\n\\end{frame}\n"

    document = parse(source, "slides.tex")
    frame = _only_record(document.records, "frame")

    assert frame.attrs == {"overlay": "2-", "options": "fragile,label=x"}
    assert frame.children[0].kind == "heading"
    assert frame.children[0].text == "A Title"
    assert frame.children[1].text == "Body"
    assert frame.children[0].source.raw == "{A Title}"


def test_item_overlay_and_label_are_separate_from_text() -> None:
    # Strip item overlays while preserving optional description labels
    source = (
        "\\begin{frame}\n"
        "\\begin{description}\n"
        "\\item[Due date]<3-> Submit Friday\n"
        "\\end{description}\n"
        "\\end{frame}\n"
    )

    document = parse(source)
    item = _only_record(document.records, "list_item")

    assert item.text == "Submit Friday"
    assert item.attrs == {"label": "Due date", "overlay": "3-"}
    assert "<3->" in item.source.raw


def test_tex_escape_macros_become_literal_text() -> None:
    # Resolve the eight escaped characters emitted as macro nodes
    source = (
        "\\begin{frame}\n"
        "Rate \\% cost \\$ set \\& tag \\# key \\_ left \\{ right \\}\n"
        "\\end{frame}\n"
    )

    document = parse(source)
    paragraph = _only_record(document.records, "paragraph")

    assert paragraph.text == "Rate % cost $ set & tag # key _ left { right }"


def test_frame_title_commands_consume_sibling_groups() -> None:
    # Consume title groups even when a macro database leaves siblings
    source = (
        "\\begin{frame}\n"
        "\\frametitle{Main title}\n"
        "\\framesubtitle{Supporting title}\n"
        "Body\n"
        "\\end{frame}\n"
    )

    document = parse(source)
    headings = _records_of_kind(document.records, "heading")

    assert len(headings) == 2
    assert headings[0].text == "Main title"
    assert headings[0].attrs == {"level": 2}
    assert headings[1].text == "Supporting title"
    assert headings[1].attrs == {"level": 2, "subtitle": True}


def test_comments_never_create_frames_or_content() -> None:
    # Ignore commented frames inline notes and trailing comments
    source = (
        "% \\begin{frame}{Hidden}\n"
        "% Hidden body\n"
        "% \\end{frame}\n"
        "\\begin{frame}{Shown}\n"
        "Visible % invisible words\n"
        "\\end{frame}\n"
    )

    document = parse(source)
    frames = _records_of_kind(document.records, "frame")
    paragraphs = _records_of_kind(document.records, "paragraph")

    assert len(frames) == 1
    assert frames[0].children[0].text == "Shown"
    assert paragraphs[0].text == "Visible"
    assert "invisible" not in paragraphs[0].source.raw


def test_unknown_macro_collects_sibling_arguments() -> None:
    # Keep unknown arguments and whether their macro was user declared
    source = (
        "\\newcommand{\\myplot}[2]{#1 #2}\n"
        "\\begin{document}\n"
        "\\begin{frame}\\myplot{results.csv}{blue}\\end{frame}\n"
        "\\end{document}\n"
    )

    document = parse(source)
    unknown = _only_record(document.records, "unknown")

    assert document.user_macros == ["myplot"]
    assert unknown.attrs == {
        "macro": "myplot",
        "args": ["results.csv", "blue"],
        "user_defined": True,
    }
    assert unknown.source.raw == "\\myplot{results.csv}{blue}"


def test_inline_and_display_math_keep_exact_tex() -> None:
    # Distinguish all walker math delimiter forms
    source = "\\begin{frame}\nInline $a+b$ and \\(c+d\\).\n\\[e+f\\]\n$$g+h$$\n\\end{frame}\n"

    document = parse(source)
    formulas = _records_of_kind(document.records, "formula")

    assert len(formulas) == 4
    assert formulas[0].attrs["tex"] == "a+b"
    assert formulas[0].attrs["inline"] is True
    assert formulas[0].source.raw == "$a+b$"
    assert formulas[1].attrs["tex"] == "c+d"
    assert formulas[1].attrs["inline"] is True
    assert formulas[2].attrs["tex"] == "e+f"
    assert formulas[2].attrs["inline"] is False
    assert formulas[3].attrs["tex"] == "g+h"
    assert formulas[3].attrs["inline"] is False


def test_math_environments_include_starred_forms() -> None:
    # Recognize equation align gather and display math environments
    source = (
        "\\begin{frame}\n"
        "\\begin{equation}a=b\\end{equation}\n"
        "\\begin{align*}c&=d\\end{align*}\n"
        "\\begin{gather}e=f\\end{gather}\n"
        "\\begin{displaymath}g=h\\end{displaymath}\n"
        "\\end{frame}\n"
    )

    document = parse(source)
    formulas = _records_of_kind(document.records, "formula")
    environments: list[str] = []
    for formula in formulas:
        environments.append(formula.attrs["environment"])

    assert environments == ["equation", "align*", "gather", "displaymath"]
    assert formulas[1].attrs["tex"] == "c&=d"


def test_tikz_keeps_raw_source_and_extracts_node_labels() -> None:
    # Preserve TikZ verbatim while ignoring braces hidden in comments
    source = (
        "\\begin{frame}\n"
        "\\begin{tikzpicture}\n"
        "% comment with {braces}\n"
        "\\node at (0,0) {Alpha};\n"
        "\\node[hidden] at (1,0) {\\small Beta};\n"
        "\\node at (2,0) {Fold \\n};\n"
        "\\end{tikzpicture}\n"
        "\\end{frame}\n"
    )

    document = parse(source)
    figure = _only_record(document.records, "figure")

    assert figure.attrs == {
        "subtype": "diagram",
        "labels": ["Alpha", "Beta", "Fold \\n"],
    }
    assert figure.source.raw.startswith("\\begin{tikzpicture}")
    assert figure.source.raw.endswith("\\end{tikzpicture}")
    assert "% comment with {braces}" in figure.source.raw


def test_environment_and_item_spans_use_precise_lines_and_offsets() -> None:
    # End environment spans on closing lines and items on final content
    source = (
        "Preamble\n"
        "\\begin{frame}{Span test}\n"
        "\\begin{itemize}\n"
        "\\item First line\n"
        "  continued\n"
        "\\item Second\n"
        "\\end{itemize}\n"
        "\\end{frame}\n"
    )

    document = parse(source, "deck.tex")
    frame = _only_record(document.records, "frame")
    items = _records_of_kind(document.records, "list_item")

    assert frame.source.file == "deck.tex"
    assert frame.source.line_start == 2
    assert frame.source.line_end == 8
    assert frame.source.char_start == source.index("\\begin{frame}")
    assert frame.source.char_end == source.index("\\end{frame}") + len("\\end{frame}")
    assert items[0].source.line_start == 4
    assert items[0].source.line_end == 5
    assert items[0].source.raw.endswith("continued")
    assert items[1].source.line_start == 6
    assert items[1].source.line_end == 6
    assert items[1].source.raw.endswith("Second")

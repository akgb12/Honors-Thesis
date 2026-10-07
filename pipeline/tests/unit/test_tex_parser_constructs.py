from pathlib import Path

from a11y_pipeline.adapters.tex_beamer.parser import parse, parse_file
from a11y_pipeline.adapters.tex_beamer.records import NativeRecord

FIXTURES = Path(__file__).parents[1] / "fixtures"


def _records_of_kind(records: list[NativeRecord], kind: str) -> list[NativeRecord]:
    # Gather matching records throughout the native tree
    matches: list[NativeRecord] = []
    for record in records:
        if record.kind == kind:
            matches.append(record)
        matches.extend(_records_of_kind(record.children, kind))
    return matches


def _frame(document_records: list[NativeRecord]) -> NativeRecord:
    # Return the only frame in a focused source sample
    frames = _records_of_kind(document_records, "frame")
    assert len(frames) == 1
    return frames[0]


def test_metadata_and_both_title_page_commands_are_recorded() -> None:
    # Capture full metadata values and title page command locations
    source = (
        "\\title[Short]{Long \\& Clear}\n"
        "\\subtitle{A Subtitle}\n"
        "\\author{An Author}\n"
        "\\date{Today}\n"
        "\\institute{A University}\n"
        "\\begin{document}\n"
        "\\begin{frame}\\titlepage\\end{frame}\n"
        "\\begin{frame}\\maketitle\\end{frame}\n"
        "\\end{document}\n"
    )

    document = parse(source)
    title_pages = _records_of_kind(document.records, "title_page")

    assert document.metadata == {
        "title": "Long & Clear",
        "subtitle": "A Subtitle",
        "author": "An Author",
        "date": "Today",
        "institute": "A University",
    }
    assert document.metadata_sources["title"].raw == "{Long \\& Clear}"
    assert len(title_pages) == 2
    assert title_pages[0].attrs["command"] == "titlepage"
    assert title_pages[1].attrs["command"] == "maketitle"


def test_lists_preserve_order_labels_nesting_and_item_math() -> None:
    # Represent all Beamer list forms with nested native children
    source = (
        "\\begin{frame}\n"
        "\\begin{itemize}\n"
        "\\item Outer $x$\n"
        "\\begin{enumerate}\\item First\\end{enumerate}\n"
        "\\end{itemize}\n"
        "\\begin{description}\\item[Key] Value\\end{description}\n"
        "\\end{frame}\n"
    )

    document = parse(source)
    lists = _records_of_kind(document.records, "list")
    items = _records_of_kind(document.records, "list_item")
    formulas = _records_of_kind(document.records, "formula")

    assert len(lists) == 3
    assert lists[0].attrs == {"ordered": False}
    assert lists[1].attrs == {"ordered": True}
    assert lists[2].attrs == {"ordered": False, "description": True}
    assert items[0].text == "Outer $x$"
    assert items[2].attrs["label"] == "Key"
    assert formulas[0].attrs == {
        "tex": "x",
        "inline": True,
        "displaytype": "inline",
    }


def test_paragraphs_split_on_blank_lines_and_semantic_blocks() -> None:
    # Split loose frame text without merging across block boundaries
    source = (
        "\\begin{frame}\n"
        "First line\n"
        "continues here.\n"
        "\n"
        "Second paragraph.\n"
        "\\includegraphics{chart}\n"
        "Third paragraph.\n"
        "\\end{frame}\n"
    )

    document = parse(source)
    paragraphs = _records_of_kind(document.records, "paragraph")
    figures = _records_of_kind(document.records, "figure")

    assert len(paragraphs) == 3
    assert paragraphs[0].text == "First line continues here."
    assert paragraphs[1].text == "Second paragraph."
    assert paragraphs[2].text == "Third paragraph."
    assert figures[0].attrs == {"path": "chart"}


def test_image_options_and_path_are_preserved() -> None:
    # Keep the complete image option text and referenced path
    source = (
        "\\begin{frame}\n"
        "\\includegraphics[width=.5\\textwidth,keepaspectratio]{figs/chart.pdf}\n"
        "\\end{frame}\n"
    )

    document = parse(source)
    figure = _records_of_kind(document.records, "figure")[0]

    assert figure.attrs == {
        "path": "figs/chart.pdf",
        "options": "width=.5\\textwidth,keepaspectratio",
    }
    assert figure.source.raw == (
        "\\includegraphics[width=.5\\textwidth,keepaspectratio]{figs/chart.pdf}"
    )


def test_blocks_emit_level_three_headings() -> None:
    # Preserve each Beamer block kind and its heading level
    source = (
        "\\begin{frame}\n"
        "\\begin{block}{One}A\\end{block}\n"
        "\\begin{alertblock}<2->{Two}B\\end{alertblock}\n"
        "\\begin{exampleblock}{Three}C\\end{exampleblock}\n"
        "\\end{frame}\n"
    )

    document = parse(source)
    blocks = _records_of_kind(document.records, "block")
    headings = _records_of_kind(document.records, "heading")

    assert len(blocks) == 3
    assert blocks[0].attrs == {"block_type": "block", "title": "One"}
    assert blocks[1].attrs == {
        "block_type": "alertblock",
        "overlay": "2-",
        "title": "Two",
    }
    assert blocks[2].attrs == {"block_type": "exampleblock", "title": "Three"}
    assert headings[0].attrs["level"] == 3
    assert headings[1].text == "Two"
    assert headings[2].text == "Three"


def test_transparent_wrappers_expose_their_content() -> None:
    # Flatten layout wrappers while retaining their visible paragraphs
    source = (
        "\\begin{frame}\n"
        "\\begin{center}Centered\\end{center}\n"
        "\\begin{columns}\n"
        "\\begin{column}{.5\\textwidth}Left\\end{column}\n"
        "\\begin{column}{.5\\textwidth}Right\\end{column}\n"
        "\\end{columns}\n"
        "\\begin{flushleft}Flush left\\end{flushleft}\n"
        "\\begin{flushright}Flush right\\end{flushright}\n"
        "\\begin{minipage}{2in}Mini\\end{minipage}\n"
        "\\end{frame}\n"
    )

    document = parse(source)
    paragraphs = _records_of_kind(document.records, "paragraph")
    texts: list[str] = []
    for paragraph in paragraphs:
        assert paragraph.text is not None
        texts.append(paragraph.text)

    assert texts == ["Centered", "Left", "Right", "Flush left", "Flush right", "Mini"]
    assert _records_of_kind(document.records, "unknown") == []


def test_overlay_commands_and_pause_count_are_recorded() -> None:
    # Capture scoped overlay specs and frame pause totals
    source = (
        "\\begin{frame}\n"
        "\\pause\n"
        "\\only<1>{One}\n"
        "\\uncover<2->{Two}\n"
        "\\onslide<3>{Three}\n"
        "\\visible<4>{Four}\n"
        "\\invisible<5>{Five}\n"
        "\\end{frame}\n"
    )

    document = parse(source)
    frame = _frame(document.records)
    overlays = _records_of_kind(document.records, "overlay")
    commands: list[str] = []
    specs: list[str] = []
    texts: list[str] = []
    for overlay in overlays:
        commands.append(overlay.attrs["command"])
        specs.append(overlay.attrs["overlay"])
        texts.append(overlay.children[0].text or "")

    assert frame.attrs["pauses"] == 1
    assert commands == ["only", "uncover", "onslide", "visible", "invisible"]
    assert specs == ["1", "2-", "3", "4", "5"]
    assert texts == ["One", "Two", "Three", "Four", "Five"]


def test_formatting_macros_are_transparent_and_spacing_is_dropped() -> None:
    # Flow formatting text while removing layout spacing arguments
    source = (
        "\\begin{frame}\n"
        "\\centering \\small Plain \\textbf{bold} \\emph{em} \\textit{italics} "
        "\\alert<2>{alerted} \\structure{structured}"
        "\\vspace{2em}\\hspace{1em} done\n"
        "\\end{frame}\n"
    )

    document = parse(source)
    paragraph = _records_of_kind(document.records, "paragraph")[0]

    assert paragraph.text == "Plain bold em italics alerted structured done"
    assert "2em" not in paragraph.text
    assert "1em" not in paragraph.text


def test_sections_definitions_and_hypersetup_are_structured() -> None:
    # Record outlines user macros and nested hyperlink values
    source = (
        "\\newcommand{\\first}[1]{#1}\n"
        "\\renewcommand{\\first}[1]{Again #1}\n"
        "\\def\\second#1{Second #1}\n"
        "\\hypersetup{pdftitle={A, B},pdflang={en-US},bookmarksopen}\n"
        "\\begin{document}\n"
        "\\section{Main}\n"
        "\\subsection{Detail}\n"
        "\\end{document}\n"
    )

    document = parse(source)
    definitions = _records_of_kind(document.records, "definition")
    sections = _records_of_kind(document.records, "section")
    setup = _records_of_kind(document.records, "hypersetup")[0]

    assert document.user_macros == ["first", "second"]
    assert len(definitions) == 3
    assert definitions[2].attrs == {"command": "def", "name": "second"}
    assert sections[0].text == "Main"
    assert sections[0].attrs["level"] == 1
    assert sections[1].text == "Detail"
    assert sections[1].attrs["level"] == 2
    assert document.hypersetup == {
        "pdftitle": "A, B",
        "pdflang": "en-US",
        "bookmarksopen": "",
    }
    assert setup.attrs["settings"] == document.hypersetup


def test_adversarial_fixture_covers_expected_native_structure() -> None:
    # Parse the complete adversarial deck before canonical IR building
    document = parse_file(FIXTURES / "adversarial")
    frames = _records_of_kind(document.records, "frame")
    items = _records_of_kind(document.records, "list_item")
    formulas = _records_of_kind(document.records, "formula")
    figures = _records_of_kind(document.records, "figure")
    unknowns = _records_of_kind(document.records, "unknown")

    assert document.source_file == "deck.tex"
    assert document.metadata["title"] == "Intro to Machine Learning"
    assert len(frames) == 4
    assert len(items) == 5
    assert len(formulas) == 2
    assert len(figures) == 2
    assert unknowns[0].attrs["macro"] == "myplot"
    assert unknowns[0].attrs["args"] == ["results.csv"]
    assert unknowns[0].attrs["user_defined"] is True
    assert frames[1].attrs["options"] == "fragile"
    assert frames[2].attrs["pauses"] == 1

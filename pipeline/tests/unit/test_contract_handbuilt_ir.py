from a11y_pipeline.ir.ids import fingerprint_source
from a11y_pipeline.ir.models import (
    Accessibility,
    Container,
    DocumentIR,
    Element,
    SourceRef,
)


def _source(line: int, native_type: str, raw: str) -> SourceRef:
    # Build a source reference for contract data
    return SourceRef(
        file="main.tex",
        line_start=line,
        line_end=line,
        char_start=line * 10,
        char_end=line * 10 + len(raw),
        native_type=native_type,
        raw=raw,
    )


def _element(
    element_id: str,
    semantic_type: str,
    parent_id: str,
    line: int,
    raw: str,
    role: str,
) -> Element:
    # Build one contract element
    return Element(
        id=element_id,
        semantic_type=semantic_type,
        parent_id=parent_id,
        content={"text": raw},
        fingerprint=fingerprint_source(raw),
        source=_source(line, semantic_type, raw),
        accessibility=Accessibility(role=role),
    )


def build_handbuilt_ir() -> DocumentIR:
    # Build the source neutral contract fixture
    first_heading = _element(
        "slide_01/heading_01",
        "heading",
        "slide_01",
        3,
        "Agenda",
        "H2",
    )
    first_list = _element("slide_01/list_01", "list", "slide_01", 4, "Topics", "L")
    first_item = _element(
        "slide_01/list_01/list_item_01",
        "list_item",
        "slide_01/list_01",
        5,
        "Accessibility",
        "LI",
    )
    first_list.child_ids = [first_item.id]

    second_heading = _element(
        "slide_02/heading_01",
        "heading",
        "slide_02",
        9,
        "Results",
        "H2",
    )
    figure = _element(
        "slide_02/figure_01",
        "figure",
        "slide_02",
        10,
        "A rising line",
        "Figure",
    )
    figure.subtype = "chart"
    figure.accessibility.status = "needs_description"

    elements = {
        first_heading.id: first_heading,
        first_list.id: first_list,
        first_item.id: first_item,
        second_heading.id: second_heading,
        figure.id: figure,
    }
    containers = [
        Container(
            id="slide_01",
            kind="slide",
            title_element_id=first_heading.id,
            element_ids=[first_heading.id, first_list.id],
        ),
        Container(
            id="slide_02",
            kind="slide",
            title_element_id=second_heading.id,
            element_ids=[second_heading.id, figure.id],
        ),
    ]
    return DocumentIR(
        document_id="contract12345678",
        source_format="tex-beamer",
        main_file="main.tex",
        metadata={"title": "Contract fixture", "lang": "en-US"},
        containers=containers,
        elements=elements,
    )


def test_handbuilt_ir_contract_scaffold() -> None:
    # Check the contract fixture has two slides and one figure
    document = build_handbuilt_ir()
    assert len(document.containers) == 2
    assert document.elements["slide_02/figure_01"].accessibility.status == "needs_description"

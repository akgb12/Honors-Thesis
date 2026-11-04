from pathlib import Path

import pikepdf
from pikepdf import Array, Dictionary, Name, String

from a11y_pipeline.evaluation.pdf_checks import (
    check_pdf,
    collect_structure_bindings,
    read_parent_tree,
    scan_page_content,
)
from a11y_pipeline.ir.ids import fingerprint_source
from a11y_pipeline.ir.models import (
    Accessibility,
    Container,
    DocumentIR,
    Element,
    RenderRef,
    SourceRef,
)


def _write_structured_pdf(
    path: Path,
    unmarked: bool = False,
    broken_parent: bool = False,
    overlay_repeat: bool = False,
) -> None:
    # Write a small tagged PDF for structural tests
    pdf = pikepdf.new()
    first_page = pdf.add_blank_page(page_size=(200, 200))
    final_page = first_page
    if overlay_repeat:
        final_page = pdf.add_blank_page(page_size=(200, 200))
    marked_stream = b"/P <</MCID 0>> BDC BT (Hello) Tj ET EMC\n"
    first_page.obj.Contents = pdf.make_stream(marked_stream)
    if overlay_repeat:
        final_page.obj.Contents = pdf.make_stream(marked_stream)
    if unmarked:
        first_page.obj.Contents = pdf.make_stream(marked_stream + b"BT (Loose) Tj ET\n")

    structure_root = pdf.make_indirect(Dictionary(Type=Name.StructTreeRoot))
    document = pdf.make_indirect(
        Dictionary(
            Type=Name.StructElem,
            S=Name.Document,
            P=structure_root,
            K=Array(),
        )
    )
    section = pdf.make_indirect(
        Dictionary(
            Type=Name.StructElem,
            S=Name.Sect,
            P=document,
            K=Array(),
        )
    )
    paragraph = pdf.make_indirect(
        Dictionary(
            Type=Name.StructElem,
            S=Name.P,
            P=section,
            Pg=final_page.obj,
            K=0,
        )
    )
    section.K.append(paragraph)
    document.K.append(section)
    structure_root.K = document

    numbers = Array()
    for page_index, page in enumerate(pdf.pages):
        page.obj.StructParents = page_index
        numbers.append(page_index)
        mapping = Array()
        if page.obj == final_page.obj and not broken_parent:
            mapping.append(paragraph)
        numbers.append(pdf.make_indirect(mapping))
    structure_root.ParentTree = pdf.make_indirect(Dictionary(Nums=numbers))
    structure_root.ParentTreeNextKey = len(pdf.pages)
    pdf.Root.StructTreeRoot = structure_root
    pdf.Root.MarkInfo = Dictionary(Marked=True)
    pdf.Root.Lang = String("en-US")
    pdf.Root.ViewerPreferences = Dictionary(DisplayDocTitle=True)
    pdf.docinfo["/Title"] = String("Tagged fixture")
    with pdf.open_metadata() as metadata:
        metadata["dc:title"] = "Tagged fixture"
    pdf.save(path)


def _overlay_ir() -> DocumentIR:
    # Build one mapped overlay element
    raw = "Hello"
    element = Element(
        id="slide_01/paragraph_01",
        semantic_type="paragraph",
        parent_id="slide_01",
        content={"text": raw},
        fingerprint=fingerprint_source(raw),
        source=SourceRef(
            file="main.tex",
            line_start=1,
            line_end=1,
            char_start=0,
            char_end=len(raw),
            native_type="paragraph",
            raw=raw,
        ),
        render=RenderRef(pages=[1, 2], mapping_method="marker", confidence=0.8),
        accessibility=Accessibility(role="P"),
        mcid=0,
    )
    return DocumentIR(
        document_id="pdfchecks1234567",
        source_format="tex-beamer",
        main_file="main.tex",
        metadata={"title": "Tagged fixture", "lang": "en-US"},
        containers=[
            Container(
                id="slide_01",
                kind="slide",
                element_ids=[element.id],
                rendered_pages=[1, 2],
            )
        ],
        elements={element.id: element},
    )


def test_content_scan_counts_mcid_and_unmarked_operators(tmp_path: Path) -> None:
    # Count marked and unmarked text showing operators
    path = tmp_path / "operators.pdf"
    _write_structured_pdf(path, unmarked=True)

    with pikepdf.open(path) as pdf:
        scan = scan_page_content(pdf.pages[0])

    assert scan.mcid_counts == {0: 1}
    assert scan.total_text_operators == 2
    assert scan.unmarked_text_operators == 1


def test_parent_tree_and_structure_helpers_find_one_owner(tmp_path: Path) -> None:
    # Resolve a ParentTree entry and its structure binding
    path = tmp_path / "helpers.pdf"
    _write_structured_pdf(path)

    with pikepdf.open(path) as pdf:
        tree = read_parent_tree(pdf.Root.StructTreeRoot.ParentTree)
        bindings = collect_structure_bindings(pdf.Root.StructTreeRoot)

    assert list(tree) == [0]
    assert len(tree[0]) == 1
    assert len(bindings) == 1
    assert bindings[0].mcid == 0
    assert bindings[0].role == "P"


def test_complete_tagged_fixture_passes_structural_checks(tmp_path: Path) -> None:
    # Pass metadata structure and ParentTree checks
    path = tmp_path / "valid.pdf"
    _write_structured_pdf(path)

    result = check_pdf(path)

    assert result.passed
    assert result.passed_check_count == len(result.checks)
    assert result.issues == []


def test_broken_parent_tree_and_unmarked_content_are_reported(tmp_path: Path) -> None:
    # Report broken ownership and unmarked text separately
    path = tmp_path / "broken.pdf"
    _write_structured_pdf(path, unmarked=True, broken_parent=True)

    result = check_pdf(path)
    codes: list[str] = []
    for issue in result.issues:
        codes.append(issue.code)

    assert "broken_mcid_link" in codes
    assert "unmarked_content" in codes
    assert not result.checks["mcid_links"]
    assert not result.passed


def test_overlay_repeat_tagged_on_earlier_page_is_reported(tmp_path: Path) -> None:
    # Reject semantic tags on an earlier overlay page
    path = tmp_path / "overlay.pdf"
    _write_structured_pdf(path, overlay_repeat=True)

    result = check_pdf(path, _overlay_ir())
    overlay_issues = []
    for issue in result.issues:
        if issue.code == "overlay_repeat_tagged":
            overlay_issues.append(issue)

    assert len(overlay_issues) == 1
    assert overlay_issues[0].details["page"] == 1
    assert not result.checks["overlay_repeats"]

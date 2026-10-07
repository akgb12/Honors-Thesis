import pytest

from a11y_pipeline.ir.models import Container, DocumentIR, Element, Patch, SourceRef
from a11y_pipeline.ir.patches import apply_patches


def _document() -> DocumentIR:
    # Build a document with one figure
    source = SourceRef(
        file="main.tex",
        line_start=4,
        line_end=8,
        char_start=40,
        char_end=100,
        native_type="tikzpicture",
        raw="\\begin{tikzpicture}\\end{tikzpicture}",
    )
    element = Element(
        id="slide_01/figure_01",
        semantic_type="figure",
        subtype="diagram",
        parent_id="slide_01",
        fingerprint="0123456789abcdef",
        source=source,
    )
    container = Container(id="slide_01", kind="slide", element_ids=[element.id])
    return DocumentIR(
        document_id="document12345678",
        source_format="tex-beamer",
        main_file="main.tex",
        containers=[container],
        elements={element.id: element},
    )


def test_apply_patches_is_pure() -> None:
    # Check patches return a changed copy
    document = _document()
    patch = Patch(
        element_id="slide_01/figure_01",
        path="accessibility.alt_text",
        value="A diagram",
        by="model",
        round=0,
    )
    result = apply_patches(document, [patch])
    assert document.elements[patch.element_id].accessibility.alt_text is None
    assert result.elements[patch.element_id].accessibility.alt_text == "A diagram"
    assert result is not document


def test_locked_element_rejects_automatic_patch() -> None:
    # Check locked human work rejects model changes
    document = _document()
    element_id = "slide_01/figure_01"
    document.elements[element_id].accessibility.locked = True
    patch = Patch(
        element_id=element_id,
        path="accessibility.alt_text",
        value="A model description",
        by="model",
        round=1,
    )
    with pytest.raises(ValueError, match="locked"):
        apply_patches(document, [patch])


def test_locked_element_accepts_human_patch() -> None:
    # Check a human can update locked work
    document = _document()
    element_id = "slide_01/figure_01"
    document.elements[element_id].accessibility.locked = True
    patch = Patch(
        element_id=element_id,
        path="accessibility.alt_text",
        value="A human description",
        by="human",
        round=1,
    )
    result = apply_patches(document, [patch])
    assert result.elements[element_id].accessibility.alt_text == "A human description"

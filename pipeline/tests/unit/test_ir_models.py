from pathlib import Path

import pytest
from pydantic import ValidationError

from a11y_pipeline.ir.models import Container, DocumentIR, Element, SourceRef
from a11y_pipeline.ir.serialize import (
    dumps_document,
    loads_document,
    read_document,
    write_document,
)


def _source() -> SourceRef:
    # Build a minimal source reference
    return SourceRef(
        file="main.tex",
        line_start=1,
        line_end=1,
        char_start=0,
        char_end=5,
        native_type="text",
        raw="Hello",
    )


def _document() -> DocumentIR:
    # Build a minimal document
    element = Element(
        id="slide_01/paragraph_01",
        semantic_type="paragraph",
        parent_id="slide_01",
        content={"text": "Hello"},
        fingerprint="185f8db32271fe25",
        source=_source(),
    )
    container = Container(id="slide_01", kind="slide", element_ids=[element.id])
    return DocumentIR(
        document_id="document12345678",
        source_format="tex-beamer",
        main_file="main.tex",
        containers=[container],
        elements={element.id: element},
    )


def test_document_json_round_trip(tmp_path: Path) -> None:
    # Check stable JSON serialization and file round trip
    document = _document()
    text = dumps_document(document)
    assert text.endswith("\n")
    assert text.index('"assets"') < text.index('"containers"')
    assert loads_document(text) == document

    output_path = tmp_path / "ir.json"
    write_document(document, output_path)
    assert read_document(output_path) == document


def test_mutable_defaults_are_isolated() -> None:
    # Check collection defaults do not leak between models
    first = _document()
    second = _document()
    first.containers[0].rendered_pages.append(1)
    assert second.containers[0].rendered_pages == []


def test_models_forbid_unknown_fields() -> None:
    # Check unknown model fields are rejected
    source_data = _source().model_dump()
    source_data["unexpected"] = True
    with pytest.raises(ValidationError):
        SourceRef.model_validate(source_data)

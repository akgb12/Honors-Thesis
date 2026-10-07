from a11y_pipeline.adapters.tex_beamer.records import (
    NativeDocument,
    NativeRecord,
    NativeSource,
)


def test_native_records_keep_source_and_nested_content() -> None:
    # Keep parser output independent from canonical IR models
    source = NativeSource(
        file="main.tex",
        line_start=2,
        line_end=2,
        char_start=5,
        char_end=10,
        native_type="paragraph",
        raw="Hello",
    )
    child = NativeRecord(kind="paragraph", source=source, text="Hello")
    frame = NativeRecord(kind="frame", source=source, children=[child])
    document = NativeDocument(
        source_file="main.tex",
        source_text="Hello",
        metadata={"title": "Example"},
        records=[frame],
    )

    assert document.records[0].children[0].text == "Hello"
    assert document.records[0].source.char_start == 5
    assert document.metadata == {"title": "Example"}

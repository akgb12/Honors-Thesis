import pytest

from a11y_pipeline.ir.ids import IdAllocator, container_id, fingerprint_source, normalize_source


def test_allocator_counts_per_parent_and_type() -> None:
    # Check identifiers advance independently by parent and type
    allocator = IdAllocator()
    assert allocator.allocate("slide_01", "paragraph") == "slide_01/paragraph_01"
    assert allocator.allocate("slide_01", "paragraph") == "slide_01/paragraph_02"
    assert allocator.allocate("slide_01", "figure") == "slide_01/figure_01"
    assert allocator.allocate("slide_02", "paragraph") == "slide_02/paragraph_01"


def test_container_identifier_is_one_based() -> None:
    # Check container identifiers use two digit numbering
    assert container_id(1) == "slide_01"
    assert container_id(12) == "slide_12"
    with pytest.raises(ValueError):
        container_id(0)


def test_fingerprint_ignores_comments_and_whitespace() -> None:
    # Check fingerprints use normalized source content
    first = "Alpha   beta % ignored\n gamma \\% value"
    second = "Alpha beta\ngamma \\% value"
    assert normalize_source(first) == "Alpha beta gamma \\% value"
    assert fingerprint_source(first) == fingerprint_source(second)
    assert len(fingerprint_source(first)) == 16

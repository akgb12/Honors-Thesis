import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops

from a11y_pipeline.ir.models import DocumentIR, Issue
from a11y_pipeline.render.pages import render_pages


@dataclass(frozen=True)
class PixelCheck:
    identical: bool
    original_pages: int
    candidate_pages: int
    different_pages: list[int]


def compare_pdf_pixels(
    original_pdf: Path,
    candidate_pdf: Path,
    dpi: int = 80,
) -> PixelCheck:
    # Compare complete PDF renders without image tolerances
    with tempfile.TemporaryDirectory(prefix="a11y-pixel-check-") as temporary:
        root = Path(temporary)
        original = render_pages(original_pdf, root / "original", dpi=dpi)
        candidate = render_pages(candidate_pdf, root / "candidate", dpi=dpi)
        different: list[int] = []
        shared = min(len(original), len(candidate))
        for index in range(shared):
            if not _images_identical(original[index], candidate[index]):
                different.append(index + 1)
        maximum = max(len(original), len(candidate))
        for page in range(shared + 1, maximum + 1):
            different.append(page)
    return PixelCheck(
        identical=not different,
        original_pages=len(original),
        candidate_pages=len(candidate),
        different_pages=different,
    )


def visual_change_issues(ir: DocumentIR, check: PixelCheck) -> list[Issue]:
    # Build page vetoes with the marked elements involved
    issues: list[Issue] = []
    for page in check.different_pages:
        element_ids: list[str] = []
        for element in ir.elements.values():
            if element.mcid is not None and page in element.render.pages:
                element_ids.append(element.id)
        issues.append(
            Issue(
                element_id=None,
                code="visual_change",
                severity="veto",
                message=f"Marked output changed rendered page {page}",
                details={"page": page, "element_ids": element_ids},
            )
        )
    return issues


def _images_identical(first_path: Path, second_path: Path) -> bool:
    # Compare one page pair with Pillow difference bounds
    with Image.open(first_path) as first_image:
        with Image.open(second_path) as second_image:
            first = first_image.convert("RGB")
            second = second_image.convert("RGB")
            if first.size != second.size:
                return False
            return ImageChops.difference(first, second).getbbox() is None

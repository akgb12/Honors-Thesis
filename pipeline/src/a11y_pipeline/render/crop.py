import math
import tempfile
from pathlib import Path

import pikepdf
from PIL import Image

from a11y_pipeline.render.pages import render_page


def crop_pdf_bbox(
    pdf_path: Path,
    page: int,
    bbox: tuple[float, float, float, float],
    output_path: Path,
    dpi: int = 200,
    padding: int = 4,
) -> Path:
    # Render and crop a PDF box with bottom left coordinate flipping
    page_box = page_box_points(pdf_path, page)
    with tempfile.TemporaryDirectory(prefix="a11y-crop-") as temporary:
        rendered = Path(temporary) / "page.png"
        render_page(pdf_path, page, rendered, dpi)
        with Image.open(rendered) as image:
            pixel_box = pdf_bbox_to_pixels(bbox, page_box, dpi, padding, image.size)
            crop = image.crop(pixel_box)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            crop.save(output_path, format="PNG")
    return output_path


def page_box_points(
    pdf_path: Path,
    page: int,
) -> tuple[float, float, float, float]:
    # Read the physical page media box in PDF points
    with pikepdf.open(pdf_path) as pdf:
        if page < 1 or page > len(pdf.pages):
            raise ValueError(f"Page {page} is outside the PDF")
        media_box = pdf.pages[page - 1].obj.MediaBox
        return (
            float(media_box[0]),
            float(media_box[1]),
            float(media_box[2]),
            float(media_box[3]),
        )


def pdf_bbox_to_pixels(
    bbox: tuple[float, float, float, float],
    page_box: tuple[float, float, float, float],
    dpi: int,
    padding: int = 0,
    image_size: tuple[int, int] | None = None,
) -> tuple[int, int, int, int]:
    # Convert bottom left PDF coordinates to top left image pixels
    if dpi <= 0 or padding < 0:
        raise ValueError("DPI must be positive and padding must not be negative")
    page_x0, page_y0, page_x1, page_y1 = page_box
    x0, y0, x1, y1 = bbox
    if x1 <= x0 or y1 <= y0:
        raise ValueError("PDF crop box must have positive area")
    scale = dpi / 72.0
    left = math.floor((x0 - page_x0) * scale) - padding
    right = math.ceil((x1 - page_x0) * scale) + padding
    top = math.floor((page_y1 - y1) * scale) - padding
    bottom = math.ceil((page_y1 - y0) * scale) + padding
    width = math.ceil((page_x1 - page_x0) * scale)
    height = math.ceil((page_y1 - page_y0) * scale)
    if image_size is not None:
        width, height = image_size
    left = max(0, min(left, width))
    right = max(0, min(right, width))
    top = max(0, min(top, height))
    bottom = max(0, min(bottom, height))
    if right <= left or bottom <= top:
        raise ValueError("Converted crop box is empty")
    return left, top, right, bottom

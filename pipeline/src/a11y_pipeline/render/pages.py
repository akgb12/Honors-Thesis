import re
import subprocess
from pathlib import Path


class RenderError(RuntimeError):
    pass


def render_pages(
    pdf_path: Path,
    output_dir: Path,
    dpi: int = 110,
    prefix: str = "page",
) -> list[Path]:
    # Render every PDF page to a separate PNG image
    if dpi <= 0:
        raise ValueError("Render DPI must be positive")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_prefix = output_dir / prefix
    completed = subprocess.run(
        ["pdftoppm", "-r", str(dpi), "-png", str(pdf_path), str(output_prefix)],
        capture_output=True,
        check=False,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RenderError(f"pdftoppm failed: {detail}")
    paths: list[Path] = []
    for path in output_dir.glob(f"{prefix}-*.png"):
        paths.append(path)
    paths.sort(key=_page_number)
    if not paths:
        raise RenderError("pdftoppm produced no page images")
    return paths


def render_page(
    pdf_path: Path,
    page: int,
    output_path: Path,
    dpi: int,
) -> Path:
    # Render one physical PDF page to a named PNG
    if page < 1 or dpi <= 0:
        raise ValueError("Page and DPI must be positive")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    prefix = output_path.with_suffix("")
    completed = subprocess.run(
        [
            "pdftoppm",
            "-f",
            str(page),
            "-l",
            str(page),
            "-singlefile",
            "-r",
            str(dpi),
            "-png",
            str(pdf_path),
            str(prefix),
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RenderError(f"pdftoppm failed: {detail}")
    generated = prefix.with_suffix(".png")
    if generated != output_path:
        generated.replace(output_path)
    if not output_path.is_file():
        raise RenderError("pdftoppm produced no page image")
    return output_path


def _page_number(path: Path) -> int:
    # Read the numeric suffix from one rendered page name
    match = re.search(r"-(\d+)\.png$", path.name)
    if match is None:
        return 0
    return int(match.group(1))

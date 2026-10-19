import re
import subprocess
import tempfile
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageStat

from a11y_pipeline.evaluation.concepts import normalize_text
from a11y_pipeline.ir.models import Element
from a11y_pipeline.render.crop import page_box_points
from a11y_pipeline.render.pages import render_page

DEFAULT_DPI = 200
DEFAULT_LUMINANCE_THRESHOLD = 20.0


class HiddenLabelError(RuntimeError):
    pass


@dataclass(frozen=True)
class WordBox:
    text: str
    bbox: tuple[float, float, float, float]
    luminance_stddev: float | None = None

    @property
    def hidden(self) -> bool:
        # Classify a measured word using the fixed threshold
        if self.luminance_stddev is None:
            return False
        return self.luminance_stddev < DEFAULT_LUMINANCE_THRESHOLD


@dataclass(frozen=True)
class HiddenLabelResult:
    page: int
    visible_labels: list[str]
    hidden_labels: list[str]
    words: list[WordBox]
    dpi: int
    threshold: float


def extract_word_boxes(pdf_path: Path, page: int) -> list[WordBox]:
    # Extract one page of Poppler word boxes
    if page < 1:
        raise ValueError("Page must be positive")
    completed = subprocess.run(
        [
            "pdftotext",
            "-f",
            str(page),
            "-l",
            str(page),
            "-bbox",
            str(pdf_path),
            "-",
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise HiddenLabelError(f"pdftotext failed: {detail}")
    try:
        root = ElementTree.fromstring(completed.stdout)
    except ElementTree.ParseError as error:
        raise HiddenLabelError("pdftotext returned invalid bbox XML") from error
    words: list[WordBox] = []
    for node in root.iter():
        if not node.tag.endswith("word"):
            continue
        text = "".join(node.itertext()).strip()
        try:
            bbox = (
                float(node.attrib["xMin"]),
                float(node.attrib["yMin"]),
                float(node.attrib["xMax"]),
                float(node.attrib["yMax"]),
            )
        except (KeyError, ValueError) as error:
            raise HiddenLabelError("pdftotext returned an invalid word box") from error
        words.append(WordBox(text=text, bbox=bbox))
    return words


def detect_figure_hidden_labels(
    pdf_path: Path,
    figure: Element,
    labels: list[str],
) -> HiddenLabelResult:
    # Detect labels on the final rendered figure page
    if figure.semantic_type != "figure":
        raise ValueError("Element must be a figure")
    if not figure.render.pages or figure.render.bbox is None:
        raise ValueError("Figure must have mapped pages and a bounding box")
    return detect_hidden_labels(
        pdf_path,
        figure.render.pages[-1],
        figure.render.bbox,
        labels,
    )


def detect_hidden_labels(
    pdf_path: Path,
    page: int,
    figure_bbox: tuple[float, float, float, float],
    labels: list[str],
    dpi: int = DEFAULT_DPI,
    threshold: float = DEFAULT_LUMINANCE_THRESHOLD,
) -> HiddenLabelResult:
    # Detect source labels hidden by a flat rendered fill
    if dpi != DEFAULT_DPI:
        raise ValueError("Hidden label detection requires 200 DPI")
    if threshold != DEFAULT_LUMINANCE_THRESHOLD:
        raise ValueError("Hidden label detection requires threshold 20")
    page_box = page_box_points(pdf_path, page)
    extracted = extract_word_boxes(pdf_path, page)
    words = _words_inside_figure(extracted, figure_bbox, page_box)
    with tempfile.TemporaryDirectory(prefix="a11y-hidden-labels-") as temporary:
        rendered = Path(temporary) / "page.png"
        render_page(pdf_path, page, rendered, dpi)
        with Image.open(rendered) as image:
            luminance = image.convert("L")
            measured = _measure_words(words, luminance, dpi)
    visible: list[str] = []
    hidden: list[str] = []
    for label in labels:
        matches = _matching_word_runs(label, measured)
        label_hidden = False
        for run in matches:
            for word in run:
                if word.luminance_stddev is not None and word.luminance_stddev < threshold:
                    label_hidden = True
                    break
            if label_hidden:
                break
        if label_hidden:
            hidden.append(label)
        elif matches:
            visible.append(label)
    return HiddenLabelResult(
        page=page,
        visible_labels=visible,
        hidden_labels=hidden,
        words=measured,
        dpi=dpi,
        threshold=threshold,
    )


def _words_inside_figure(
    words: list[WordBox],
    figure_bbox: tuple[float, float, float, float],
    page_box: tuple[float, float, float, float],
) -> list[WordBox]:
    # Select words whose centers fall inside the figure
    page_x0, page_y0, _, page_y1 = page_box
    x0, y0, x1, y1 = figure_bbox
    top = page_y1 - (y1 - page_y0)
    bottom = page_y1 - (y0 - page_y0)
    selected: list[WordBox] = []
    for word in words:
        left, word_top, right, word_bottom = word.bbox
        center_x = (left + right) / 2
        center_y = (word_top + word_bottom) / 2
        if x0 - page_x0 <= center_x <= x1 - page_x0 and top <= center_y <= bottom:
            selected.append(word)
    return selected


def _measure_words(words: list[WordBox], luminance: Image.Image, dpi: int) -> list[WordBox]:
    # Measure rendered luminance variation within each word box
    scale = dpi / 72.0
    measured: list[WordBox] = []
    for word in words:
        left = max(0, round(word.bbox[0] * scale))
        top = max(0, round(word.bbox[1] * scale))
        right = min(luminance.width, round(word.bbox[2] * scale))
        bottom = min(luminance.height, round(word.bbox[3] * scale))
        standard_deviation = 0.0
        if right > left and bottom > top:
            crop = luminance.crop((left, top, right, bottom))
            standard_deviation = float(ImageStat.Stat(crop).stddev[0])
        measured.append(
            WordBox(
                text=word.text,
                bbox=word.bbox,
                luminance_stddev=standard_deviation,
            )
        )
    return measured


def _matching_word_runs(label: str, words: list[WordBox]) -> list[list[WordBox]]:
    # Match a source label against extracted word runs, ignoring hyphens, spacing and line breaks
    target = _squash(label)
    runs: list[list[WordBox]] = []
    if not target:
        return runs
    keys = [_squash(word.text) for word in words]
    for start, first_key in enumerate(keys):
        if not first_key or not target.startswith(first_key):
            continue
        run = [words[start]]
        accumulated = first_key
        current_index = start
        while accumulated != target:
            next_index = _next_continuing_word(keys, current_index, accumulated, target)
            if next_index is None:
                break
            accumulated += keys[next_index]
            run.append(words[next_index])
            current_index = next_index
        if accumulated == target:
            runs.append(run)
    return runs


def _next_continuing_word(
    keys: list[str],
    current_index: int,
    accumulated: str,
    target: str,
) -> int | None:
    # Find the next nearby word that continues the label, across wrapped lines
    stop = min(len(keys), current_index + 4)
    for index in range(current_index + 1, stop):
        if keys[index] and target.startswith(accumulated + keys[index]):
            return index
    return None


def _squash(value: str) -> str:
    # Keep only letters and digits so hyphenation and wrapping cannot break a match
    return re.sub(r"[\W_]+", "", normalize_text(value))

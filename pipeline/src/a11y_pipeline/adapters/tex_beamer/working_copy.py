import shutil
from dataclasses import dataclass
from pathlib import Path

from a11y_pipeline.bundle.bundle import Bundle
from a11y_pipeline.ir.models import DocumentIR


@dataclass(frozen=True)
class WorkingCopies:
    original: Path
    marked: Path


def create_working_copies(
    bundle: Bundle,
    ir: DocumentIR,
    work_root: Path,
) -> WorkingCopies:
    # Create isolated source copies with safe image fallbacks
    original = work_root / "original"
    marked = work_root / "marked"
    if original.exists() or marked.exists():
        raise FileExistsError("Working copy destinations must not already exist")
    _copy_bundle(bundle, original)
    _copy_bundle(bundle, marked)
    replacements = _missing_image_replacements(ir)
    _apply_replacements(original, replacements)
    _apply_replacements(marked, replacements)
    return WorkingCopies(original=original, marked=marked)


def _copy_bundle(bundle: Bundle, destination: Path) -> None:
    # Copy normalized project files without touching source inputs
    destination.mkdir(parents=True)
    for relative in bundle.files:
        source = bundle.root / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _missing_image_replacements(
    ir: DocumentIR,
) -> dict[str, list[tuple[int, int, str]]]:
    # Build replacements directly from canonical source spans
    replacements: dict[str, list[tuple[int, int, str]]] = {}
    for element in ir.elements.values():
        if element.semantic_type != "figure" or element.subtype != "image":
            continue
        asset_id = element.content.get("asset_id")
        asset = ir.assets.get(str(asset_id))
        if asset is None or asset.status != "missing":
            continue
        width = _image_width(element.attrs.get("options"))
        path = _escape_texttt(asset.referenced_as)
        placeholder = (
            rf"\fbox{{\parbox[c][3cm][c]{{{width}}}"
            rf"{{\centering\small missing: \texttt{{{path}}}}}}}"
        )
        file_replacements = replacements.setdefault(element.source.file, [])
        file_replacements.append((element.source.char_start, element.source.char_end, placeholder))
    return replacements


def _image_width(options: object) -> str:
    # Preserve an explicit image width in the placeholder box
    if not isinstance(options, str):
        return r"\linewidth"
    for option in _split_options(options):
        key, separator, value = option.partition("=")
        if separator and key.strip() == "width" and value.strip():
            return value.strip()
    return r"\linewidth"


def _split_options(options: str) -> list[str]:
    # Split image options only at top level commas
    parts: list[str] = []
    start = 0
    depth = 0
    for index, character in enumerate(options):
        if character == "{":
            depth += 1
        elif character == "}" and depth:
            depth -= 1
        elif character == "," and depth == 0:
            parts.append(options[start:index])
            start = index + 1
    parts.append(options[start:])
    return parts


def _escape_texttt(value: str) -> str:
    # Escape special text characters for the fallback label
    replacements = {
        "\\": r"\textbackslash{}",
        "{": r"\{",
        "}": r"\}",
        "#": r"\#",
        "$": r"\$",
        "%": r"\%",
        "&": r"\&",
        "_": r"\_",
    }
    escaped = ""
    for character in value:
        escaped += replacements.get(character, character)
    return escaped


def _apply_replacements(
    root: Path,
    replacements: dict[str, list[tuple[int, int, str]]],
) -> None:
    # Apply nonoverlapping span edits from the end of each file
    for relative, edits in replacements.items():
        path = root / relative
        text = path.read_text(encoding="utf-8")
        ordered = sorted(edits, key=lambda edit: edit[0], reverse=True)
        previous_start = len(text) + 1
        for start, end, replacement in ordered:
            if end > previous_start or start < 0 or end > len(text):
                raise ValueError(f"Invalid or overlapping source span in {relative}")
            text = text[:start] + replacement + text[end:]
            previous_start = start
        path.write_text(text, encoding="utf-8")

import difflib
import re
import shutil
import textwrap
from dataclasses import dataclass
from pathlib import Path

from a11y_pipeline.adapters.tex_beamer.compile import CompileResult, compile_project
from a11y_pipeline.bundle.bundle import Bundle
from a11y_pipeline.ir.models import DocumentIR, Element, Issue
from a11y_pipeline.render.pixeldiff import PixelCheck, compare_pdf_pixels
from a11y_pipeline.synthesis.plan import OutputOperation

ALT_PREFIX = "% a11y-alt: "


@dataclass(frozen=True)
class WriterResult:
    project_root: Path
    diff_path: Path
    issues: list[Issue]
    operations: list[OutputOperation]


@dataclass(frozen=True)
class UpdatedProjectVerification:
    compile_result: CompileResult
    pixel_check: PixelCheck


def write_updated_project(
    bundle: Bundle,
    ir: DocumentIR,
    output_root: Path,
    diff_path: Path | None = None,
) -> WriterResult:
    # Copy and update a project without changing its input
    if output_root.exists():
        raise FileExistsError("Updated project destination already exists")
    output_root.mkdir(parents=True)
    original_text: dict[str, str] = {}
    for relative in bundle.files:
        source = bundle.root / relative
        target = output_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if source.suffix.lower() == ".tex":
            original_text[relative] = source.read_text(encoding="utf-8")
    operations: list[OutputOperation] = []
    issues: list[Issue] = []
    edits: dict[str, list[tuple[int, int, str]]] = {}
    _add_metadata_edit(ir, original_text, edits, operations)
    _add_figure_edits(ir, original_text, edits, operations, issues)
    _apply_source_edits(output_root, edits)
    if diff_path is None:
        diff_path = output_root.parent / "changes.diff"
    _write_diff(bundle, output_root, edits, diff_path)
    return WriterResult(
        project_root=output_root,
        diff_path=diff_path,
        issues=issues,
        operations=operations,
    )


def verify_updated_project(
    original_pdf: Path,
    project_root: Path,
    main_file: str,
    dpi: int = 80,
    timeout_seconds: int = 180,
) -> UpdatedProjectVerification:
    # Compile an updated project and compare every rendered page
    compile_result = compile_project(project_root, main_file, timeout_seconds)
    pixel_check = compare_pdf_pixels(original_pdf, compile_result.pdf_path, dpi=dpi)
    return UpdatedProjectVerification(
        compile_result=compile_result,
        pixel_check=pixel_check,
    )


def _add_metadata_edit(
    ir: DocumentIR,
    original_text: dict[str, str],
    edits: dict[str, list[tuple[int, int, str]]],
    operations: list[OutputOperation],
) -> None:
    # Add or merge the required hyperlink metadata
    text = original_text.get(ir.main_file)
    if text is None:
        raise FileNotFoundError(f"Main TeX file was not copied: {ir.main_file}")
    title = ir.metadata.get("title", "").strip()
    language = ir.metadata.get("lang", "").strip() or "en-US"
    title_setting = "pdftitle={" + title + "}"
    language_setting = "pdflang={" + language + "}"
    groups = _macro_groups(text, "hypersetup")
    if groups:
        start, end, body_start, body_end = groups[-1]
        body = text[body_start:body_end]
        merged = _merge_hypersetup(body, title_setting, language_setting)
        replacement = text[start:body_start] + merged + text[body_end:end]
        _append_edit(edits, ir.main_file, start, end, replacement)
        operation = "merge_hypersetup"
    else:
        position = _preamble_insertion_position(text)
        command = "\\hypersetup{" + title_setting + ", " + language_setting + "}\n"
        _append_edit(edits, ir.main_file, position, position, command)
        operation = "add_hypersetup"
    operations.append(
        OutputOperation(
            output="updated_source",
            operation=operation,
            source_file=ir.main_file,
            details={"title": title, "language": language},
        )
    )


def _add_figure_edits(
    ir: DocumentIR,
    original_text: dict[str, str],
    edits: dict[str, list[tuple[int, int, str]]],
    operations: list[OutputOperation],
    issues: list[Issue],
) -> None:
    # Add source annotations for figures with descriptions
    for element in ir.elements.values():
        if element.semantic_type != "figure":
            continue
        description = _figure_description(element)
        if description is None:
            issues.append(
                Issue(
                    element_id=element.id,
                    code="alt_missing",
                    severity="error",
                    message="Figure source was not updated because alternative text is missing",
                    details={"status": element.accessibility.status},
                )
            )
            continue
        text = original_text.get(element.source.file)
        if text is None:
            raise FileNotFoundError(f"Figure source file was not copied: {element.source.file}")
        if element.subtype == "image":
            raw = text[element.source.char_start : element.source.char_end]
            replacement = _update_includegraphics(raw, _escape_alt(description))
            _append_edit(
                edits,
                element.source.file,
                element.source.char_start,
                element.source.char_end,
                replacement,
            )
            operation = "add_image_alt"
        elif element.source.native_type == "tikzpicture":
            insertion = _tikz_alt_comment(text, element.source.char_start, description)
            _append_edit(
                edits,
                element.source.file,
                element.source.char_start,
                element.source.char_start,
                insertion,
            )
            operation = "add_tikz_alt"
        else:
            continue
        operations.append(
            OutputOperation(
                output="updated_source",
                operation=operation,
                element_id=element.id,
                source_file=element.source.file,
            )
        )


def _figure_description(element: Element) -> str | None:
    # Combine short and extended figure descriptions
    if element.accessibility.status in {"missing_asset", "failed"}:
        return None
    alt_text = element.accessibility.alt_text
    if alt_text is None or not alt_text.strip():
        return None
    description = alt_text.strip()
    extended = element.accessibility.extended_description
    if extended is not None and extended.strip():
        description += "\n\n" + extended.strip()
    return description


def _escape_alt(value: str) -> str:
    # Escape required TeX option characters
    escaped = ""
    replacements = {"{": r"\{", "}": r"\}", "%": r"\%", "#": r"\#"}
    for character in value:
        escaped += replacements.get(character, character)
    return escaped


def _update_includegraphics(raw: str, escaped_alt: str) -> str:
    # Add or replace one includegraphics alt option
    match = re.match(r"\\includegraphics\s*", raw)
    if match is None:
        raise ValueError("Image source span is not an includegraphics command")
    option_start = match.end()
    if option_start < len(raw) and raw[option_start] == "[":
        option_end = _balanced_end(raw, option_start, "[", "]")
        body = raw[option_start + 1 : option_end - 1]
        merged = _merge_option(body, "alt", escaped_alt)
        return raw[: option_start + 1] + merged + raw[option_end - 1 :]
    option = "[alt={" + escaped_alt + "}]"
    return raw[:option_start] + option + raw[option_start:]


def _merge_option(body: str, key: str, value: str) -> str:
    # Replace one top level option while preserving others
    kept: list[str] = []
    for option in _split_top_level(body):
        option_key, separator, _ = option.partition("=")
        if separator and option_key.strip() == key:
            continue
        if option.strip():
            kept.append(option.strip())
    kept.append(key + "={" + value + "}")
    return ",".join(kept)


def _tikz_alt_comment(text: str, position: int, description: str) -> str:
    # Wrap TikZ alternative text comments to one hundred columns
    line_start = text.rfind("\n", 0, position) + 1
    indentation = text[line_start:position]
    if not indentation.isspace():
        indentation = ""
    paragraphs = description.splitlines()
    comment_lines: list[str] = []
    for paragraph in paragraphs:
        if not paragraph.strip():
            comment_lines.append(ALT_PREFIX.rstrip())
            continue
        wrapped = textwrap.wrap(
            paragraph.strip(),
            width=100 - len(ALT_PREFIX) - len(indentation),
            break_long_words=True,
            break_on_hyphens=False,
        )
        for line in wrapped:
            comment_lines.append(ALT_PREFIX + line)
    insertion = ""
    for index, line in enumerate(comment_lines):
        if index > 0:
            insertion += indentation
        insertion += line + "\n"
    insertion += indentation
    return insertion


def _merge_hypersetup(
    body: str,
    title_setting: str,
    language_setting: str,
) -> str:
    # Merge required values into an existing hypersetup body
    kept: list[str] = []
    for setting in _split_top_level(body):
        key, separator, _ = setting.partition("=")
        normalized = key.strip().lower()
        if separator and normalized in {"pdftitle", "pdflang"}:
            continue
        if setting.strip():
            kept.append(setting.strip())
    kept.append(title_setting)
    kept.append(language_setting)
    return ", ".join(kept)


def _split_top_level(value: str) -> list[str]:
    # Split comma separated TeX values outside groups
    parts: list[str] = []
    start = 0
    brace_depth = 0
    bracket_depth = 0
    for index, character in enumerate(value):
        if character == "{" and not _escaped(value, index):
            brace_depth += 1
        elif character == "}" and not _escaped(value, index) and brace_depth:
            brace_depth -= 1
        elif character == "[" and not _escaped(value, index):
            bracket_depth += 1
        elif character == "]" and not _escaped(value, index) and bracket_depth:
            bracket_depth -= 1
        elif character == "," and brace_depth == 0 and bracket_depth == 0:
            parts.append(value[start:index])
            start = index + 1
    parts.append(value[start:])
    return parts


def _macro_groups(text: str, macro: str) -> list[tuple[int, int, int, int]]:
    # Locate uncommented macro argument groups
    groups: list[tuple[int, int, int, int]] = []
    pattern = re.compile(r"\\" + re.escape(macro) + r"\s*\{")
    for match in pattern.finditer(text):
        if _is_commented(text, match.start()):
            continue
        opening = match.end() - 1
        end = _balanced_end(text, opening, "{", "}")
        groups.append((match.start(), end, opening + 1, end - 1))
    return groups


def _preamble_insertion_position(text: str) -> int:
    # Find the line after the last preamble package command
    package_ends = _macro_command_ends(text, "usepackage")
    if package_ends:
        return _line_end(text, package_ends[-1])
    class_ends = _macro_command_ends(text, "documentclass")
    if not class_ends:
        raise ValueError("Main TeX file has no documentclass command")
    return _line_end(text, class_ends[-1])


def _macro_command_ends(text: str, macro: str) -> list[int]:
    # Locate complete preamble commands with optional arguments
    ends: list[int] = []
    pattern = re.compile(r"\\" + re.escape(macro) + r"\s*")
    for match in pattern.finditer(text):
        if _is_commented(text, match.start()):
            continue
        position = match.end()
        if position < len(text) and text[position] == "[":
            position = _balanced_end(text, position, "[", "]")
            while position < len(text) and text[position].isspace() and text[position] != "\n":
                position += 1
        if position >= len(text) or text[position] != "{":
            continue
        ends.append(_balanced_end(text, position, "{", "}"))
    return ends


def _balanced_end(text: str, opening: int, left: str, right: str) -> int:
    # Find the exclusive end of one balanced group
    depth = 0
    for index in range(opening, len(text)):
        character = text[index]
        if character == left and not _escaped(text, index):
            depth += 1
        elif character == right and not _escaped(text, index):
            depth -= 1
            if depth == 0:
                return index + 1
    raise ValueError("Unbalanced TeX group")


def _escaped(text: str, position: int) -> bool:
    # Detect a character preceded by an odd backslash count
    count = 0
    index = position - 1
    while index >= 0 and text[index] == "\\":
        count += 1
        index -= 1
    return count % 2 == 1


def _is_commented(text: str, position: int) -> bool:
    # Detect a macro after an active percent on its line
    line_start = text.rfind("\n", 0, position) + 1
    for index in range(line_start, position):
        if text[index] == "%" and not _escaped(text, index):
            return True
    return False


def _line_end(text: str, position: int) -> int:
    # Return the position after the current line ending
    newline = text.find("\n", position)
    if newline < 0:
        return len(text)
    return newline + 1


def _append_edit(
    edits: dict[str, list[tuple[int, int, str]]],
    source_file: str,
    start: int,
    end: int,
    replacement: str,
) -> None:
    # Record one source edit
    file_edits = edits.setdefault(source_file, [])
    file_edits.append((start, end, replacement))


def _apply_source_edits(
    output_root: Path,
    edits: dict[str, list[tuple[int, int, str]]],
) -> None:
    # Apply nonoverlapping edits from the end of each file
    for relative, file_edits in edits.items():
        path = output_root / relative
        text = path.read_text(encoding="utf-8")
        ordered = sorted(file_edits, key=lambda edit: edit[0], reverse=True)
        previous_start = len(text) + 1
        for start, end, replacement in ordered:
            if start < 0 or end < start or end > previous_start or end > len(text):
                raise ValueError(f"Invalid or overlapping source edit in {relative}")
            text = text[:start] + replacement + text[end:]
            previous_start = start
        path.write_text(text, encoding="utf-8")


def _write_diff(
    bundle: Bundle,
    output_root: Path,
    edits: dict[str, list[tuple[int, int, str]]],
    diff_path: Path,
) -> None:
    # Write one unified diff for all updated source files
    output = ""
    for relative in sorted(edits):
        original = (bundle.root / relative).read_text(encoding="utf-8")
        updated = (output_root / relative).read_text(encoding="utf-8")
        lines = difflib.unified_diff(
            original.splitlines(keepends=True),
            updated.splitlines(keepends=True),
            fromfile="a/" + relative,
            tofile="b/" + relative,
        )
        for line in lines:
            output += line
    diff_path.parent.mkdir(parents=True, exist_ok=True)
    diff_path.write_text(output, encoding="utf-8")

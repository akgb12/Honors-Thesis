import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from a11y_pipeline.adapters.tex_beamer.working_copy import (
    _missing_image_replacements,
)
from a11y_pipeline.ir.models import DocumentIR, Element, Issue


@dataclass(frozen=True)
class InjectionRecord:
    id: str
    mcid: int
    tag: str
    alt: str | None


def inject_markers(
    ir: DocumentIR,
    marked_root: Path,
    injection_table_path: Path | None = None,
) -> list[InjectionRecord]:
    # Inject invisible markers and assign container local identifiers
    events: dict[str, list[tuple[int, int, str]]] = {}
    records: list[InjectionRecord] = []
    replacements = _missing_image_replacements(ir)
    for container in ir.containers:
        ordered = _reading_order(ir, container.element_ids)
        options = str(container.attrs.get("options", ""))
        if "fragile" in options.lower():
            _record_fragile_issue(ir, container.id)
            continue
        mcid = 0
        for element in ordered:
            tag = _marker_tag(element)
            if tag is None:
                continue
            element.mcid = mcid
            key = element.id.replace("/", "-")
            prefix, suffix = _marker_text(key, mcid, tag, element.semantic_type)
            start, end = _content_bounds(element)
            start = _translated_position(replacements, element.source.file, start, False)
            end = _translated_position(replacements, element.source.file, end, True)
            file_events = events.setdefault(element.source.file, [])
            file_events.append((start, 1, prefix))
            file_events.append((end, 0, suffix))
            short_form = _metadata_short_form(element, marked_root, replacements)
            if short_form is not None:
                group_start = _translated_position(
                    replacements,
                    element.source.file,
                    element.source.char_start,
                    False,
                )
                file_events.append((group_start, 0, short_form))
            records.append(
                InjectionRecord(
                    id=element.id,
                    mcid=mcid,
                    tag=tag,
                    alt=_marker_alt(element),
                )
            )
            mcid += 1
    _apply_insertions(marked_root, events)
    _insert_macro_blocks(marked_root / ir.main_file)
    if injection_table_path is not None:
        write_injection_table(records, injection_table_path)
    return records


def write_injection_table(records: list[InjectionRecord], path: Path) -> None:
    # Write marker metadata as stable readable JSON
    data: list[dict[str, Any]] = []
    for record in records:
        data.append(asdict(record))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def _reading_order(ir: DocumentIR, element_ids: list[str]) -> list[Element]:
    # Flatten semantic descendants in deterministic reading order
    ordered: list[Element] = []
    for element_id in element_ids:
        element = ir.elements[element_id]
        ordered.append(element)
        descendants = _reading_order(ir, element.child_ids)
        ordered.extend(descendants)
    return ordered


def _record_fragile_issue(ir: DocumentIR, container_id: str) -> None:
    # Record one warning for a frame that cannot be marked safely
    for issue in ir.issues:
        if issue.code == "unmarked_fragile" and issue.details.get("container_id") == container_id:
            return
    ir.issues.append(
        Issue(
            element_id=None,
            code="unmarked_fragile",
            severity="warning",
            message=f"Fragile frame {container_id} was left unmarked",
            details={"container_id": container_id},
        )
    )


def _marker_tag(element: Element) -> str | None:
    # Select elements that can be safely marked
    if element.semantic_type == "heading":
        return element.accessibility.role or "H2"
    if element.semantic_type == "document_title":
        return "H1"
    if element.semantic_type == "paragraph":
        return "P"
    if element.semantic_type == "list_item":
        return "LBody"
    if element.semantic_type == "formula" and not element.content.get("inline", False):
        return "Formula"
    if element.semantic_type == "figure":
        return "Figure"
    return None


def _marker_text(
    key: str,
    mcid: int,
    tag: str,
    semantic_type: str,
) -> tuple[str, str]:
    # Build one matching marker wrapper
    if semantic_type == "figure":
        return rf"\aelfigure{{{key}}}{{{mcid}}}{{", "}"
    return rf"\aelspan{{{key}}}{{{mcid}}}{{{tag}}}{{", "}"


def _marker_alt(element: Element) -> str | None:
    # Select structural alternative text for the injection table
    if element.semantic_type == "formula":
        return element.fidelity.signature
    if element.semantic_type == "figure":
        return element.accessibility.alt_text
    return None


def _metadata_short_form(
    element: Element,
    root: Path,
    replacements: dict[str, list[tuple[int, int, str]]],
) -> str | None:
    # Preserve plain metadata text for Beamer expansion
    field = element.attrs.get("metadata_field")
    if field not in {"title", "author", "institute", "date"}:
        return None
    start = _translated_position(
        replacements,
        element.source.file,
        element.source.char_start,
        False,
    )
    text = (root / element.source.file).read_text(encoding="utf-8")
    line_start = text.rfind("\n", 0, start) + 1
    prefix = text[line_start:start]
    macro = re.search(rf"\\{field}\s*(\[[^\]]*\])?\s*$", prefix)
    if macro is None or macro.group(1) is not None:
        return None
    raw = element.source.raw or ""
    return f"[{raw[1:-1]}]"


def _content_bounds(element: Element) -> tuple[int, int]:
    # Locate the safe marker body inside the exact source span
    raw = element.source.raw or ""
    base = element.source.char_start
    if element.semantic_type in {"heading", "document_title"}:
        return base + 1, base + len(raw) - 1
    if element.attrs.get("metadata_field") is not None:
        return base + 1, base + len(raw) - 1
    if element.semantic_type == "list_item":
        relative_start, relative_end = _list_item_bounds(raw)
        return base + relative_start, base + relative_end
    if element.semantic_type == "paragraph":
        relative_start, relative_end = _paragraph_bounds(raw)
        return base + relative_start, base + relative_end
    if element.semantic_type == "formula":
        relative_start, relative_end = _display_math_bounds(raw)
        return base + relative_start, base + relative_end
    return element.source.char_start, element.source.char_end


def _list_item_bounds(raw: str) -> tuple[int, int]:
    # Exclude item syntax overlays and nested lists
    match = re.match(r"\\item(?:\[[^\]]*\])?(?:<[^>]*>)?\s*", raw)
    if match is None:
        raise ValueError("List item source does not begin with an item command")
    start = match.end()
    nested = re.search(r"\\begin\{(?:itemize|enumerate|description)\}", raw[start:])
    end = len(raw)
    if nested is not None:
        end = start + nested.start()
    while end > start and raw[end - 1].isspace():
        end -= 1
    return start, end


def _paragraph_bounds(raw: str) -> tuple[int, int]:
    # Keep spacing commands and outer font declarations outside markers
    spacing = re.match(r"(?:\\(?:vspace|hspace)\*?\s*\{[^{}]*\}\s*)*", raw)
    start = 0
    if spacing is not None:
        start = spacing.end()
    declaration = re.match(
        r"\{\\(?:tiny|scriptsize|footnotesize|small|normalsize|large|Large|LARGE|huge|Huge)"
        r"\s+",
        raw[start:],
    )
    if declaration is not None and raw.endswith("}"):
        return start + declaration.end(), len(raw) - 1
    return 0, len(raw)


def _display_math_bounds(raw: str) -> tuple[int, int]:
    # Place formula markers inside delimiters or environments
    if raw.startswith(r"\[") and raw.endswith(r"\]"):
        return 2, _trim_math_end(raw, 2, len(raw) - 2)
    if raw.startswith("$$") and raw.endswith("$$"):
        return 2, _trim_math_end(raw, 2, len(raw) - 2)
    environment = re.match(r"\\begin\{[^}]+\}", raw)
    if environment is not None:
        closing = raw.rfind(r"\end{")
        if closing >= environment.end():
            return environment.end(), _trim_math_end(raw, environment.end(), closing)
    raise ValueError("Unsupported display formula source")


def _trim_math_end(raw: str, start: int, end: int) -> int:
    # Leave trailing formula whitespace outside the marker
    while end > start and raw[end - 1].isspace():
        end -= 1
    return end


def _translated_position(
    replacements: dict[str, list[tuple[int, int, str]]],
    source_file: str,
    position: int,
    at_end: bool,
) -> int:
    # Translate original offsets after missing image replacements
    delta = 0
    edits = replacements.get(source_file, [])
    ordered = sorted(edits, key=lambda edit: edit[0])
    for start, end, replacement in ordered:
        if position < start:
            break
        if position > end or position == end:
            delta += len(replacement) - (end - start)
            continue
        if position == start:
            if at_end:
                return start + delta + len(replacement)
            return start + delta
        raise ValueError("Marker boundary falls inside a replaced image span")
    return position + delta


def _apply_insertions(
    root: Path,
    events: dict[str, list[tuple[int, int, str]]],
) -> None:
    # Apply grouped insertions from the end of each marked file
    for relative, file_events in events.items():
        path = root / relative
        text = path.read_text(encoding="utf-8")
        grouped: dict[int, list[tuple[int, str]]] = {}
        for position, category, value in file_events:
            values = grouped.setdefault(position, [])
            values.append((category, value))
        for position in sorted(grouped, reverse=True):
            values = sorted(grouped[position], key=lambda item: item[0])
            insertion = ""
            for _, value in values:
                insertion += value
            text = text[:position] + insertion + text[position:]
        path.write_text(text, encoding="utf-8")


def _insert_macro_blocks(main_path: Path) -> None:
    # Place verified marker definitions around the complete preamble
    text = main_path.read_text(encoding="utf-8")
    block_a = _macro_block("marker_macros_block_a.tex")
    block_b = _macro_block("marker_macros_block_b.tex")
    document_class = re.search(
        r"^[^\n]*\\documentclass(?:\[[^\]]*\])?\{[^}]+\}[^\n]*\n",
        text,
        re.M,
    )
    if document_class is None:
        raise ValueError("Main TeX file has no documentclass line")
    text = text[: document_class.end()] + block_a + text[document_class.end() :]
    begin_document = text.find(r"\begin{document}")
    if begin_document < 0:
        raise ValueError("Main TeX file has no document environment")
    text = text[:begin_document] + block_b + text[begin_document:]
    main_path.write_text(text, encoding="utf-8")


def _macro_block(name: str) -> str:
    # Read one bundled verified marker block
    path = Path(__file__).with_name(name)
    text = path.read_text(encoding="utf-8")
    if not text.endswith("\n"):
        text += "\n"
    return text

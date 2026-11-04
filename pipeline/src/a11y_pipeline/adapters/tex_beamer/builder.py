import hashlib
import re
from pathlib import PurePosixPath
from typing import Any

from a11y_pipeline.adapters.tex_beamer.preflight import PreflightResult
from a11y_pipeline.adapters.tex_beamer.records import (
    NativeDocument,
    NativeRecord,
    NativeSource,
)
from a11y_pipeline.ir.ids import IdAllocator, container_id, fingerprint_source
from a11y_pipeline.ir.models import (
    Accessibility,
    Asset,
    Classification,
    Container,
    DocumentIR,
    Element,
    Fidelity,
    Issue,
    SemanticType,
    SourceRef,
)

ROLE_BY_TYPE = {
    "document_title": "H1",
    "paragraph": "P",
    "list": "L",
    "list_item": "LI",
    "formula": "Formula",
    "figure": "Figure",
    "title_page": "Sect",
}


class _Builder:
    def __init__(
        self,
        document: NativeDocument,
        preflight_result: PreflightResult | None,
    ):
        # Prepare stable state for one IR build
        self.document = document
        self.preflight_result = preflight_result
        self.allocator = IdAllocator()
        self.elements: dict[str, Element] = {}
        self.assets: dict[str, Asset] = {}
        self.issues: list[Issue] = []
        self.asset_sequence = 0
        self._add_preflight_assets()
        self._add_preflight_issues()

    def run(self) -> DocumentIR:
        # Build containers and elements in source order
        containers: list[Container] = []
        frame_index = 0
        for record in self.document.records:
            if record.kind != "frame":
                continue
            frame_index += 1
            containers.append(self._frame(record, frame_index))
        metadata = dict(self.document.metadata)
        metadata["lang"] = self.document.hypersetup.get("pdflang", "en-US")
        document_hash = hashlib.sha256(self.document.source_text.encode("utf-8")).hexdigest()
        return DocumentIR(
            document_id=document_hash[:16],
            source_format="tex-beamer",
            main_file=self.document.source_file,
            metadata=metadata,
            containers=containers,
            elements=self.elements,
            assets=self.assets,
            issues=self.issues,
        )

    def _frame(self, record: NativeRecord, index: int) -> Container:
        # Convert one frame into a slide container
        slide_id = container_id(index)
        attrs = dict(record.attrs)
        attrs["_line_start"] = record.source.line_start
        attrs["_line_end"] = record.source.line_end
        element_ids: list[str] = []
        for child in record.children:
            element_ids.extend(self._records(child, slide_id, {}))
        title_element_id = None
        for element_id in element_ids:
            element = self.elements[element_id]
            if element.semantic_type == "heading" and element.attrs.get("level") == 2:
                title_element_id = element_id
                break
            if element.semantic_type == "title_page":
                for child_id in element.child_ids:
                    child = self.elements[child_id]
                    if child.semantic_type == "document_title":
                        title_element_id = child_id
                        break
                if title_element_id is not None:
                    break
        return Container(
            id=slide_id,
            kind="slide",
            title_element_id=title_element_id,
            element_ids=element_ids,
            attrs=attrs,
        )

    def _records(
        self,
        record: NativeRecord,
        parent_id: str,
        inherited_attrs: dict[str, Any],
    ) -> list[str]:
        # Build semantic records while flattening native wrappers
        if record.kind == "block":
            return self._flatten(record, parent_id, inherited_attrs)
        if record.kind == "overlay":
            overlay_attrs = dict(inherited_attrs)
            if "overlay" in record.attrs:
                overlay_attrs["overlay"] = record.attrs["overlay"]
            if "command" in record.attrs:
                overlay_attrs["overlay_command"] = record.attrs["command"]
            return self._flatten(record, parent_id, overlay_attrs)
        if record.kind in {"definition", "hypersetup", "section"}:
            return []
        element = self._element(record, parent_id, inherited_attrs)
        return [element.id]

    def _flatten(
        self,
        record: NativeRecord,
        parent_id: str,
        inherited_attrs: dict[str, Any],
    ) -> list[str]:
        # Expose children of a nonsemantic native wrapper
        element_ids: list[str] = []
        for child in record.children:
            element_ids.extend(self._records(child, parent_id, inherited_attrs))
        return element_ids

    def _element(
        self,
        record: NativeRecord,
        parent_id: str,
        inherited_attrs: dict[str, Any],
    ) -> Element:
        # Convert one native record and its children
        semantic_type = self._semantic_type(record)
        element_id = self.allocator.allocate(parent_id, semantic_type)
        attrs = dict(record.attrs)
        attrs.update(inherited_attrs)
        content: dict[str, Any] = {}
        subtype = None
        status = "done"
        role = ROLE_BY_TYPE.get(semantic_type)
        if semantic_type == "heading":
            content["text"] = record.text or ""
            content["level"] = attrs.get("level", 2)
            role = "H2"
            if content["level"] == 3:
                role = "H3"
        elif semantic_type == "paragraph" or semantic_type == "list_item":
            content["text"] = record.text or ""
        elif semantic_type == "formula":
            content["tex"] = attrs.pop("tex", "")
            content["inline"] = attrs.pop("inline", False)
        elif semantic_type == "figure":
            subtype, status = self._figure(record, element_id, content, attrs)
        elif semantic_type == "unknown":
            status = "not_handled"
        source = self._source(record.source)
        element = Element(
            id=element_id,
            semantic_type=semantic_type,
            subtype=subtype,
            parent_id=parent_id,
            content=content,
            attrs=attrs,
            fingerprint=fingerprint_source(record.source.raw),
            source=source,
            classification=Classification(evidence=[record.source.native_type]),
            accessibility=Accessibility(role=role, status=status),
            fidelity=Fidelity(signature=self._signature(semantic_type, content)),
        )
        self.elements[element_id] = element
        if semantic_type == "title_page":
            self._title_page_children(element)
        else:
            for child in record.children:
                element.child_ids.extend(self._records(child, element_id, {}))
        if semantic_type == "unknown":
            self._unknown_issue(element)
        return element

    def _semantic_type(self, record: NativeRecord) -> SemanticType:
        # Map parser kinds onto canonical types
        supported = {
            "heading",
            "paragraph",
            "list",
            "list_item",
            "formula",
            "figure",
            "title_page",
            "unknown",
        }
        if record.kind in supported:
            return record.kind
        return "unknown"

    def _signature(self, semantic_type: SemanticType, content: dict[str, Any]) -> str | None:
        # Select the fidelity signature for semantic content
        if semantic_type == "formula":
            tex = content.get("tex")
            if isinstance(tex, str):
                return tex
        text = content.get("text")
        if isinstance(text, str):
            return _collapse(text)
        return None

    def _title_page_children(self, title_page: Element) -> None:
        # Add visible metadata beneath the title page section
        fields = (
            ("title", "document_title"),
            ("subtitle", "paragraph"),
            ("author", "paragraph"),
            ("institute", "paragraph"),
            ("date", "paragraph"),
        )
        for field_name, semantic_type in fields:
            value = self.document.metadata.get(field_name)
            native_source = self.document.metadata_sources.get(field_name)
            if value is None or native_source is None:
                continue
            element_id = self.allocator.allocate(title_page.id, semantic_type)
            role = ROLE_BY_TYPE[semantic_type]
            child = Element(
                id=element_id,
                semantic_type=semantic_type,
                parent_id=title_page.id,
                content={"text": value},
                attrs={"metadata_field": field_name},
                fingerprint=fingerprint_source(native_source.raw),
                source=self._source(native_source),
                classification=Classification(evidence=[native_source.native_type]),
                accessibility=Accessibility(role=role),
                fidelity=Fidelity(signature=_collapse(value)),
            )
            self.elements[element_id] = child
            title_page.child_ids.append(element_id)

    def _figure(
        self,
        record: NativeRecord,
        element_id: str,
        content: dict[str, Any],
        attrs: dict[str, Any],
    ) -> tuple[str, str]:
        # Build an image or embedded diagram figure
        if record.source.native_type == "tikzpicture":
            labels = attrs.pop("labels", [])
            attrs["tikz_labels"] = labels
            content["source"] = {"raw": record.source.raw}
            return "diagram", "needs_description"
        reference = str(attrs.pop("path", ""))
        asset = self._image_asset(reference)
        content["asset_id"] = asset.id
        asset.used_by.append(element_id)
        if asset.status == "found":
            return "image", "needs_description"
        return "image", "missing_asset"

    def _image_asset(self, reference: str) -> Asset:
        # Match an image reference to preflight assets
        matches: list[Asset] = []
        for asset in self.assets.values():
            if asset.resolved_path is None:
                continue
            if _asset_matches(reference, asset.resolved_path):
                matches.append(asset)
        if len(matches) == 1:
            matches[0].referenced_as = reference
            return matches[0]
        if len(matches) > 1:
            return self._new_asset(reference, None, "ambiguous")
        missing = self._new_asset(reference, None, "missing")
        if self.preflight_result is None:
            self.issues.append(
                Issue(
                    element_id=None,
                    code="missing_image",
                    severity="warning",
                    message=f"Image dependency was not found: {reference}",
                    details={"dependency": reference},
                )
            )
        return missing

    def _add_preflight_assets(self) -> None:
        # Import resolved dependencies in stable order
        if self.preflight_result is None:
            return
        for path in self.preflight_result.assets:
            self._new_asset(path, path, "found")

    def _new_asset(
        self,
        referenced_as: str,
        resolved_path: str | None,
        status: str,
    ) -> Asset:
        # Allocate one stable external asset
        self.asset_sequence += 1
        asset = Asset(
            id=f"asset_{self.asset_sequence:02d}",
            referenced_as=referenced_as,
            resolved_path=resolved_path,
            status=status,
            origin="external_file",
        )
        self.assets[asset.id] = asset
        return asset

    def _add_preflight_issues(self) -> None:
        # Convert preflight findings into canonical issues
        if self.preflight_result is None:
            return
        for issue in self.preflight_result.issues:
            severity = "warning"
            if issue.severity == "critical":
                severity = "error"
            details: dict[str, Any] = {
                "source_file": issue.source_file,
                "line": issue.line,
            }
            if issue.dependency is not None:
                details["dependency"] = issue.dependency
            self.issues.append(
                Issue(
                    element_id=None,
                    code=issue.code,
                    severity=severity,
                    message=issue.message,
                    details=details,
                )
            )

    def _unknown_issue(self, element: Element) -> None:
        # Record unsupported source without discarding it
        name = element.attrs.get("macro") or element.attrs.get("environment") or "construct"
        self.issues.append(
            Issue(
                element_id=element.id,
                code="not_handled",
                severity="warning",
                message=f"TeX {name} is not handled",
            )
        )

    def _source(self, source: NativeSource) -> SourceRef:
        # Copy native provenance into the canonical source model
        return SourceRef(
            file=source.file,
            line_start=source.line_start,
            line_end=source.line_end,
            char_start=source.char_start,
            char_end=source.char_end,
            native_type=source.native_type,
            raw=source.raw,
        )


def build(
    document: NativeDocument,
    preflight_result: PreflightResult | None = None,
) -> DocumentIR:
    # Build canonical IR from parser and preflight records
    return _Builder(document, preflight_result).run()


def summarize(ir: DocumentIR) -> str:
    # Render the deterministic golden summary format
    lines: list[str] = []
    for container in ir.containers:
        line_start = container.attrs.get("_line_start", 0)
        line_end = container.attrs.get("_line_end", 0)
        details = _summary_details(container.attrs, None, ir)
        line = f"{container.id} | {container.kind} | {line_start}-{line_end} |"
        if details:
            line += f" {details}"
        lines.append(line)
        for element_id in container.element_ids:
            _summarize_element(ir, element_id, lines)
    return "\n".join(lines) + "\n"


def _summarize_element(ir: DocumentIR, element_id: str, lines: list[str]) -> None:
    # Append one element and its descendants in reading order
    element = ir.elements[element_id]
    details = _summary_details(element.attrs, element, ir)
    line = (
        f"{element.id} | {element.semantic_type} | "
        f"{element.source.line_start}-{element.source.line_end} |"
    )
    if details:
        line += f" {details}"
    lines.append(line)
    for child_id in element.child_ids:
        _summarize_element(ir, child_id, lines)


def _summary_details(
    attrs: dict[str, Any],
    element: Element | None,
    ir: DocumentIR,
) -> str:
    # Format supported details in the documented order
    values: list[tuple[str, Any]] = []
    if element is not None and element.accessibility.role is not None:
        values.append(("role", element.accessibility.role))
    if element is not None and "text" in element.content:
        values.append(("text", element.content["text"]))
    if element is not None and "tex" in element.content:
        values.append(("tex", element.content["tex"]))
        values.append(("inline", element.content.get("inline", False)))
    if element is not None and element.subtype is not None:
        values.append(("subtype", element.subtype))
    if element is not None and "asset_id" in element.content:
        asset_id = element.content["asset_id"]
        asset = ir.assets.get(asset_id)
        if asset is not None:
            values.append(("asset", asset.referenced_as))
    if element is not None and element.accessibility.status != "done":
        values.append(("status", element.accessibility.status))
    if "tikz_labels" in attrs:
        values.append(("labels", attrs["tikz_labels"]))
    detail_keys = (
        "overlay",
        "ordered",
        "options",
        "pauses",
        "macro",
        "args",
        "user_defined",
    )
    for key in detail_keys:
        if key in attrs:
            if key == "options" and element is not None:
                continue
            values.append((key, attrs[key]))
    parts: list[str] = []
    for key, value in values:
        parts.append(f"{key}={_summary_value(value)}")
    return ", ".join(parts)


def _summary_value(value: Any) -> str:
    # Normalize one scalar or sequence for golden output
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, list):
        items: list[str] = []
        for item in value:
            items.append(_collapse(str(item)))
        return _escape_commas(", ".join(items))
    return _escape_commas(_collapse(str(value)))


def _collapse(value: str) -> str:
    # Collapse whitespace without changing TeX tokens
    return re.sub(r"\s+", " ", value).strip()


def _escape_commas(value: str) -> str:
    # Escape commas reserved by the summary format
    return value.replace(",", r"\,")


def _asset_matches(reference: str, resolved_path: str) -> bool:
    # Compare references with extension and graphic path fallbacks
    reference_path = PurePosixPath(reference)
    resolved = PurePosixPath(resolved_path)
    if resolved == reference_path:
        return True
    resolved_without_suffix = resolved.with_suffix("")
    reference_without_suffix = reference_path.with_suffix("")
    if resolved_without_suffix == reference_without_suffix:
        return True
    if resolved_without_suffix.as_posix().endswith("/" + reference_without_suffix.as_posix()):
        return True
    if reference_path.parent == PurePosixPath("."):
        return resolved_without_suffix.name == reference_without_suffix.name
    return False

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pikepdf
from pikepdf import Array, Dictionary, Name, String

from a11y_pipeline.ir.models import DocumentIR, Element, Issue
from a11y_pipeline.synthesis.plan import OutputOperation


@dataclass(frozen=True)
class TaggingResult:
    pdf_path: Path
    issues: list[Issue]
    operations: list[OutputOperation]


class _StructureBuilder:
    def __init__(
        self,
        pdf: pikepdf.Pdf,
        ir: DocumentIR,
        structure_root: Any,
        document: Any,
        available_mcids: list[set[int]],
    ):
        # Prepare one deterministic structure build
        self.pdf = pdf
        self.ir = ir
        self.structure_root = structure_root
        self.document = document
        self.available_mcids = available_mcids
        self.per_page: dict[int, dict[int, Any]] = {}
        self.issues: list[Issue] = []
        self.operations: list[OutputOperation] = []

    def build(self) -> None:
        # Build container sections in document order
        for container in self.ir.containers:
            section = self._make_structure("Sect", self.document)
            for element_id in container.element_ids:
                self._add_element(section, element_id)

    def _add_element(self, parent: Any, element_id: str) -> None:
        # Add one semantic subtree in reading order
        element = self.ir.elements[element_id]
        if element.semantic_type == "title_page":
            section = self._make_structure("Sect", parent)
            for child_id in element.child_ids:
                self._add_element(section, child_id)
            return
        if element.semantic_type == "list":
            list_node = self._make_structure("L", parent)
            for child_id in element.child_ids:
                self._add_element(list_node, child_id)
            return
        if element.semantic_type == "list_item":
            item_node = self._make_structure("LI", parent)
            if element.mcid is not None:
                self._add_marked_leaf(item_node, element, "LBody")
            for child_id in element.child_ids:
                child = self.ir.elements[child_id]
                if child.semantic_type == "list":
                    self._add_element(item_node, child_id)
            return
        if element.mcid is None:
            return
        role = element.accessibility.role
        if role is None:
            return
        self._add_marked_leaf(parent, element, role)

    def _add_marked_leaf(self, parent: Any, element: Element, role: str) -> None:
        # Link one final page marker to its structure element
        if not element.render.pages:
            self._marker_issue(element, "Tagged element has no mapped page")
            return
        final_page = element.render.pages[-1]
        if final_page < 1 or final_page > len(self.pdf.pages):
            self._marker_issue(element, "Tagged element maps outside the PDF page range")
            return
        mcid = element.mcid
        if mcid is None or mcid not in self.available_mcids[final_page - 1]:
            self._marker_issue(element, "Tagged element marker is missing on its final page")
            return
        page_mapping = self.per_page.setdefault(final_page, {})
        if mcid in page_mapping:
            self._marker_issue(element, "Tagged element MCID collides on its final page")
            return
        leaf = self._make_structure(role, parent)
        leaf.Pg = self.pdf.pages[final_page - 1].obj
        leaf.K = mcid
        alt_text = _structure_alt(element, self.issues)
        if alt_text is not None:
            leaf.Alt = String(alt_text)
        page_mapping[mcid] = leaf
        self.operations.append(
            OutputOperation(
                output="tagged_pdf",
                operation="tag_content",
                element_id=element.id,
                page=final_page,
                details={"mcid": mcid, "role": role},
            )
        )

    def _make_structure(self, role: str, parent: Any) -> Any:
        # Create and append one indirect structure element
        element = self.pdf.make_indirect(
            Dictionary(
                Type=Name.StructElem,
                S=Name("/" + role),
                P=parent,
                K=Array(),
            )
        )
        parent.K.append(element)
        return element

    def _marker_issue(self, element: Element, message: str) -> None:
        # Report a marker that cannot be linked safely
        self.issues.append(
            Issue(
                element_id=element.id,
                code="tag_marker_missing",
                severity="error",
                message=message,
            )
        )


def tag_pdf(
    marked_pdf: Path,
    ir: DocumentIR,
    output_pdf: Path,
) -> TaggingResult:
    # Build a tagged PDF from marked content and mapped IR
    issues: list[Issue] = []
    operations: list[OutputOperation] = []
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    with pikepdf.open(marked_pdf) as pdf:
        available_mcids = _available_mcids(pdf)
        structure_root = pdf.make_indirect(Dictionary(Type=Name.StructTreeRoot))
        document = pdf.make_indirect(
            Dictionary(
                Type=Name.StructElem,
                S=Name.Document,
                P=structure_root,
                K=Array(),
            )
        )
        structure_root.K = document
        builder = _StructureBuilder(
            pdf,
            ir,
            structure_root,
            document,
            available_mcids,
        )
        builder.build()
        issues.extend(builder.issues)
        operations.extend(builder.operations)
        _rewrite_overlay_repeats(pdf, ir, builder.per_page, issues, operations)
        _build_parent_tree(pdf, structure_root, builder.per_page)
        _set_document_metadata(pdf, ir, structure_root, operations)
        pdf.save(output_pdf)
    return TaggingResult(
        pdf_path=output_pdf,
        issues=issues,
        operations=operations,
    )


def _available_mcids(pdf: pikepdf.Pdf) -> list[set[int]]:
    # Read marked content identifiers before rewriting overlays
    pages: list[set[int]] = []
    for page in pdf.pages:
        identifiers: set[int] = set()
        for operands, operator in pikepdf.parse_content_stream(page):
            if str(operator) != "BDC" or len(operands) < 2:
                continue
            properties = operands[1]
            if not isinstance(properties, Dictionary):
                continue
            value = properties.get("/MCID")
            try:
                identifiers.add(int(value))
            except (TypeError, ValueError):
                continue
        pages.append(identifiers)
    return pages


def _rewrite_overlay_repeats(
    pdf: pikepdf.Pdf,
    ir: DocumentIR,
    per_page: dict[int, dict[int, Any]],
    issues: list[Issue],
    operations: list[OutputOperation],
) -> None:
    # Rewrite earlier overlay markers as artifacts
    repeats: dict[int, dict[int, list[str]]] = {}
    for element in ir.elements.values():
        if element.mcid is None or len(element.render.pages) < 2:
            continue
        for page_number in element.render.pages[:-1]:
            page_repeats = repeats.setdefault(page_number, {})
            ids = page_repeats.setdefault(element.mcid, [])
            ids.append(element.id)
    for page_number, page_repeats in repeats.items():
        if page_number < 1 or page_number > len(pdf.pages):
            _repeat_page_issue(page_number, page_repeats, issues)
            continue
        final_mcids = per_page.get(page_number, {})
        targets: set[int] = set()
        for mcid in page_repeats:
            if mcid not in final_mcids:
                targets.add(mcid)
        rewritten = _rewrite_page_artifacts(pdf, page_number, targets)
        for mcid in targets:
            element_ids = page_repeats[mcid]
            if mcid not in rewritten:
                for element_id in element_ids:
                    issues.append(
                        Issue(
                            element_id=element_id,
                            code="overlay_marker_missing",
                            severity="error",
                            message="Overlay repeat marker could not be rewritten as an artifact",
                            details={"page": page_number, "mcid": mcid},
                        )
                    )
                continue
            for element_id in element_ids:
                operations.append(
                    OutputOperation(
                        output="tagged_pdf",
                        operation="artifact_overlay",
                        element_id=element_id,
                        page=page_number,
                        details={"mcid": mcid},
                    )
                )


def _rewrite_page_artifacts(
    pdf: pikepdf.Pdf,
    page_number: int,
    targets: set[int],
) -> set[int]:
    # Replace selected BDC markers without changing drawing operators
    page = pdf.pages[page_number - 1]
    rewritten: set[int] = set()
    output: list[tuple[Any, Any]] = []
    for operands, operator in pikepdf.parse_content_stream(page):
        mcid = _matching_mcid(operands, operator, targets)
        if mcid is None:
            output.append((operands, operator))
            continue
        output.append(([Name.Artifact], pikepdf.Operator("BMC")))
        rewritten.add(mcid)
    page.obj.Contents = pdf.make_stream(pikepdf.unparse_content_stream(output))
    return rewritten


def _matching_mcid(
    operands: Any,
    operator: Any,
    targets: set[int],
) -> int | None:
    # Match one semantic marker selected for artifact rewriting
    if str(operator) != "BDC" or len(operands) < 2:
        return None
    properties = operands[1]
    if not isinstance(properties, Dictionary):
        return None
    try:
        mcid = int(properties.get("/MCID"))
    except (TypeError, ValueError):
        return None
    if mcid not in targets:
        return None
    return mcid


def _repeat_page_issue(
    page_number: int,
    page_repeats: dict[int, list[str]],
    issues: list[Issue],
) -> None:
    # Report repeat mappings outside the PDF
    for mcid, element_ids in page_repeats.items():
        for element_id in element_ids:
            issues.append(
                Issue(
                    element_id=element_id,
                    code="overlay_page_invalid",
                    severity="error",
                    message="Overlay repeat maps outside the PDF page range",
                    details={"page": page_number, "mcid": mcid},
                )
            )


def _build_parent_tree(
    pdf: pikepdf.Pdf,
    structure_root: Any,
    per_page: dict[int, dict[int, Any]],
) -> None:
    # Build one ParentTree array for every PDF page
    numbers = Array()
    for page_number, page in enumerate(pdf.pages, start=1):
        key = page_number - 1
        page.obj.StructParents = key
        mapping = per_page.get(page_number, {})
        values = Array()
        if mapping:
            highest_mcid = max(mapping)
            for mcid in range(highest_mcid + 1):
                values.append(mapping.get(mcid))
        numbers.append(key)
        numbers.append(pdf.make_indirect(values))
    structure_root.ParentTree = pdf.make_indirect(Dictionary(Nums=numbers))
    structure_root.ParentTreeNextKey = len(pdf.pages)


def _set_document_metadata(
    pdf: pikepdf.Pdf,
    ir: DocumentIR,
    structure_root: Any,
    operations: list[OutputOperation],
) -> None:
    # Set required tagged PDF metadata
    title = ir.metadata.get("title", "").strip()
    if not title:
        title = "Untitled document"
    language = ir.metadata.get("lang", "").strip()
    if not language:
        language = "en-US"
    pdf.Root.StructTreeRoot = structure_root
    mark_info = pdf.Root.get("/MarkInfo")
    if not isinstance(mark_info, Dictionary):
        mark_info = Dictionary()
    mark_info.Marked = True
    pdf.Root.MarkInfo = mark_info
    pdf.Root.Lang = String(language)
    preferences = pdf.Root.get("/ViewerPreferences")
    if not isinstance(preferences, Dictionary):
        preferences = Dictionary()
    preferences.DisplayDocTitle = True
    pdf.Root.ViewerPreferences = preferences
    with pdf.open_metadata() as metadata:
        metadata["dc:title"] = title
    pdf.docinfo["/Title"] = String(title)
    operations.append(
        OutputOperation(
            output="tagged_pdf",
            operation="set_document_metadata",
            details={"title": title, "language": language},
        )
    )


def _structure_alt(element: Element, issues: list[Issue]) -> str | None:
    # Select exact formula or figure alternative text
    if element.semantic_type == "formula":
        signature = element.fidelity.signature
        if signature:
            return signature
        issues.append(
            Issue(
                element_id=element.id,
                code="formula_alt_missing",
                severity="error",
                message="Formula source is missing for alternative text",
            )
        )
        return None
    if element.semantic_type != "figure":
        return None
    if element.accessibility.status in {"missing_asset", "failed"}:
        issues.append(
            Issue(
                element_id=element.id,
                code="alt_missing",
                severity="error",
                message="Figure alternative text is unavailable",
                details={"status": element.accessibility.status},
            )
        )
        return None
    alt_text = element.accessibility.alt_text
    if alt_text is None or not alt_text.strip():
        issues.append(
            Issue(
                element_id=element.id,
                code="alt_missing",
                severity="error",
                message="Figure alternative text is missing",
                details={"status": element.accessibility.status},
            )
        )
        return None
    combined = alt_text.strip()
    extended = element.accessibility.extended_description
    if extended is not None and extended.strip():
        combined += "\n\n" + extended.strip()
    return combined

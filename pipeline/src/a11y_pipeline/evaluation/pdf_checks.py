from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pikepdf

from a11y_pipeline.ir.models import DocumentIR, Issue

TEXT_SHOWING_OPERATORS = {"Tj", "TJ", "'", '"'}


@dataclass(frozen=True)
class PageContentScan:
    page: int
    mcid_counts: dict[int, int]
    total_text_operators: int
    unmarked_text_operators: int


@dataclass(frozen=True)
class McidBinding:
    page_key: tuple[int, int] | tuple[str, int]
    mcid: int
    structure_key: tuple[int, int] | tuple[str, int]
    role: str


@dataclass(frozen=True)
class PdfCheckResult:
    checks: dict[str, bool]
    issues: list[Issue]
    pages: list[PageContentScan]
    structure_bindings: list[McidBinding] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        # Report success when no error or veto issue exists
        for issue in self.issues:
            if issue.severity in {"error", "veto"}:
                return False
        return True

    @property
    def passed_check_count(self) -> int:
        # Count successful structural checks
        count = 0
        for value in self.checks.values():
            if value:
                count += 1
        return count


def check_pdf(
    pdf_path: Path,
    ir: DocumentIR | None = None,
) -> PdfCheckResult:
    # Run structural metadata overlay and operator checks
    issues: list[Issue] = []
    checks: dict[str, bool] = {}
    scans: list[PageContentScan] = []
    bindings: list[McidBinding] = []
    with pikepdf.open(pdf_path) as pdf:
        root = pdf.Root
        mark_info = root.get("/MarkInfo")
        checks["marked"] = _dictionary_truth(mark_info, "/Marked")
        _require_check(
            checks["marked"],
            issues,
            "pdf_not_marked",
            "PDF MarkInfo does not declare marked content",
        )
        language = root.get("/Lang")
        checks["language"] = language is not None and bool(str(language).strip())
        _require_check(
            checks["language"],
            issues,
            "pdf_language_missing",
            "PDF document language is missing",
        )
        info_title = pdf.docinfo.get("/Title")
        checks["info_title"] = info_title is not None and bool(str(info_title).strip())
        _require_check(
            checks["info_title"],
            issues,
            "pdf_title_missing",
            "PDF document information title is missing",
        )
        checks["xmp_title"] = _has_xmp_title(pdf)
        _require_check(
            checks["xmp_title"],
            issues,
            "pdf_xmp_title_missing",
            "PDF XMP title is missing",
        )
        viewer = root.get("/ViewerPreferences")
        checks["display_document_title"] = _dictionary_truth(viewer, "/DisplayDocTitle")
        _require_check(
            checks["display_document_title"],
            issues,
            "pdf_display_title_disabled",
            "PDF viewer preferences do not display the document title",
        )
        structure_root = root.get("/StructTreeRoot")
        checks["structure_tree"] = structure_root is not None
        _require_check(
            checks["structure_tree"],
            issues,
            "structure_tree_missing",
            "PDF structure tree is missing",
        )
        page_numbers: dict[tuple[int, int] | tuple[str, int], int] = {}
        for page_number, page in enumerate(pdf.pages, start=1):
            page_numbers[_object_key(page.obj)] = page_number
            scan = scan_page_content(page, page_number)
            scans.append(scan)
            if scan.unmarked_text_operators > 0:
                issues.append(
                    Issue(
                        element_id=None,
                        code="unmarked_content",
                        severity="warning",
                        message=f"Page {page_number} has unmarked text showing operators",
                        details={
                            "page": page_number,
                            "count": scan.unmarked_text_operators,
                            "total": scan.total_text_operators,
                        },
                    )
                )
        parent_tree: dict[int, Any] = {}
        if structure_root is not None:
            parent_tree_object = structure_root.get("/ParentTree")
            if parent_tree_object is not None:
                parent_tree = read_parent_tree(parent_tree_object)
            bindings = collect_structure_bindings(structure_root)
        checks["parent_tree"] = bool(parent_tree)
        _require_check(
            checks["parent_tree"],
            issues,
            "parent_tree_missing",
            "PDF structure ParentTree is missing or empty",
        )
        link_issues = _validate_mcid_links(pdf, scans, parent_tree, bindings)
        issues.extend(link_issues)
        checks["mcid_links"] = not link_issues
        overlay_issues: list[Issue] = []
        completeness_issues: list[Issue] = []
        if ir is not None:
            overlay_issues = _overlay_repeat_issues(pdf, ir, scans)
            completeness_issues = _structure_completeness_issues(
                pdf,
                ir,
                bindings,
                page_numbers,
            )
            issues.extend(overlay_issues)
            issues.extend(completeness_issues)
        checks["overlay_repeats"] = not overlay_issues
        checks["structure_completeness"] = not completeness_issues
    return PdfCheckResult(
        checks=checks,
        issues=issues,
        pages=scans,
        structure_bindings=bindings,
    )


def scan_page_content(page: pikepdf.Page, page_number: int = 1) -> PageContentScan:
    # Count MCIDs and text operators by marked content scope
    stack: list[bool] = []
    mcid_counts: dict[int, int] = {}
    total_text = 0
    unmarked_text = 0
    for operands, operator in pikepdf.parse_content_stream(page):
        name = str(operator)
        if name == "BDC":
            mcid = _mcid_from_operands(operands)
            stack.append(True)
            if mcid is not None:
                mcid_counts[mcid] = mcid_counts.get(mcid, 0) + 1
            continue
        if name == "BMC":
            stack.append(True)
            continue
        if name == "EMC":
            if stack:
                stack.pop()
            continue
        if name in TEXT_SHOWING_OPERATORS:
            total_text += 1
            if not stack:
                unmarked_text += 1
    return PageContentScan(
        page=page_number,
        mcid_counts=mcid_counts,
        total_text_operators=total_text,
        unmarked_text_operators=unmarked_text,
    )


def read_parent_tree(number_tree: Any) -> dict[int, Any]:
    # Flatten a PDF number tree into key values
    values: dict[int, Any] = {}
    _read_number_tree_node(number_tree, values)
    return values


def collect_structure_bindings(structure_root: Any) -> list[McidBinding]:
    # Collect every structure element ownership binding
    bindings: list[McidBinding] = []
    children = structure_root.get("/K")
    _visit_structure_value(children, None, None, bindings)
    return bindings


def _dictionary_truth(value: Any, key: str) -> bool:
    # Read one Boolean dictionary value safely
    if value is None:
        return False
    try:
        return bool(value.get(key, False))
    except (AttributeError, ValueError):
        return False


def _has_xmp_title(pdf: pikepdf.Pdf) -> bool:
    # Check XMP Dublin Core title metadata
    try:
        with pdf.open_metadata(
            set_pikepdf_as_editor=False,
            update_docinfo=False,
        ) as metadata:
            value = metadata.get("dc:title")
            if isinstance(value, str):
                return bool(value.strip())
            if value is not None:
                return bool(str(value).strip())
    except (KeyError, TypeError, ValueError, pikepdf.PdfError):
        return False
    return False


def _require_check(
    passed: bool,
    issues: list[Issue],
    code: str,
    message: str,
) -> None:
    # Record one failed required PDF check
    if passed:
        return
    issues.append(
        Issue(
            element_id=None,
            code=code,
            severity="error",
            message=message,
        )
    )


def _mcid_from_operands(operands: Any) -> int | None:
    # Read an inline MCID property from BDC operands
    if len(operands) < 2:
        return None
    properties = operands[1]
    try:
        value = properties.get("/MCID")
    except AttributeError:
        return None
    return _integer_value(value)


def _integer_value(value: Any) -> int | None:
    # Convert a PDF integer while rejecting other objects
    if isinstance(value, bool) or value is None:
        return None
    try:
        converted = int(value)
    except (TypeError, ValueError):
        return None
    if str(value).strip() != str(converted):
        return None
    return converted


def _object_key(value: Any) -> tuple[int, int] | tuple[str, int]:
    # Build a stable key for direct or indirect PDF objects
    try:
        object_number, generation = value.objgen
        if object_number != 0:
            return int(object_number), int(generation)
    except (AttributeError, TypeError, ValueError):
        pass
    return "direct", id(value)


def _read_number_tree_node(node: Any, values: dict[int, Any]) -> None:
    # Read number pairs and child nodes recursively
    try:
        numbers = node.get("/Nums")
    except AttributeError:
        return
    if numbers is not None:
        index = 0
        while index + 1 < len(numbers):
            key = _integer_value(numbers[index])
            if key is not None:
                values[key] = numbers[index + 1]
            index += 2
    kids = node.get("/Kids")
    if kids is not None:
        for child in kids:
            _read_number_tree_node(child, values)


def _visit_structure_value(
    value: Any,
    inherited_page: Any,
    owner: Any,
    bindings: list[McidBinding],
) -> None:
    # Walk structure children and marked content references
    if value is None:
        return
    if isinstance(value, pikepdf.Array):
        for child in value:
            _visit_structure_value(child, inherited_page, owner, bindings)
        return
    integer = _integer_value(value)
    if integer is not None:
        if inherited_page is not None and owner is not None:
            bindings.append(
                McidBinding(
                    page_key=_object_key(inherited_page),
                    mcid=integer,
                    structure_key=_object_key(owner),
                    role=_structure_role(owner),
                )
            )
        return
    if not isinstance(value, pikepdf.Dictionary):
        return
    object_type = str(value.get("/Type", ""))
    if object_type == "/MCR" or value.get("/MCID") is not None:
        page = value.get("/Pg", inherited_page)
        mcid = _integer_value(value.get("/MCID"))
        if page is not None and mcid is not None and owner is not None:
            bindings.append(
                McidBinding(
                    page_key=_object_key(page),
                    mcid=mcid,
                    structure_key=_object_key(owner),
                    role=_structure_role(owner),
                )
            )
        return
    page = value.get("/Pg", inherited_page)
    children = value.get("/K")
    _visit_structure_value(children, page, value, bindings)


def _structure_role(structure: Any) -> str:
    # Read a structure element role without its name prefix
    role = str(structure.get("/S", ""))
    return role.removeprefix("/")


def _validate_mcid_links(
    pdf: pikepdf.Pdf,
    scans: list[PageContentScan],
    parent_tree: dict[int, Any],
    bindings: list[McidBinding],
) -> list[Issue]:
    # Verify every used MCID has one matching structure owner
    issues: list[Issue] = []
    bindings_by_content: dict[tuple[tuple[int, int] | tuple[str, int], int], list[McidBinding]] = {}
    for binding in bindings:
        key = (binding.page_key, binding.mcid)
        owners = bindings_by_content.setdefault(key, [])
        owners.append(binding)
    for page_index, page in enumerate(pdf.pages):
        scan = scans[page_index]
        page_key = _object_key(page.obj)
        struct_parents = _integer_value(page.obj.get("/StructParents"))
        parent_array = None
        if struct_parents is not None:
            parent_array = parent_tree.get(struct_parents)
        for mcid in scan.mcid_counts:
            owners = bindings_by_content.get((page_key, mcid), [])
            parent_keys = _parent_entry_keys(parent_array, mcid)
            owner_keys: set[tuple[int, int] | tuple[str, int]] = set()
            for owner in owners:
                owner_keys.add(owner.structure_key)
            if len(owner_keys) == 1 and parent_keys == owner_keys:
                continue
            issues.append(
                Issue(
                    element_id=None,
                    code="broken_mcid_link",
                    severity="error",
                    message=f"Page {scan.page} MCID {mcid} lacks exactly one ParentTree owner",
                    details={
                        "page": scan.page,
                        "mcid": mcid,
                        "structure_owner_count": len(owner_keys),
                        "parent_owner_count": len(parent_keys),
                    },
                )
            )
    return issues


def _parent_entry_keys(
    parent_array: Any,
    mcid: int,
) -> set[tuple[int, int] | tuple[str, int]]:
    # Read structure owner keys from one ParentTree array entry
    keys: set[tuple[int, int] | tuple[str, int]] = set()
    if parent_array is None or not isinstance(parent_array, pikepdf.Array):
        return keys
    if mcid < 0 or mcid >= len(parent_array):
        return keys
    entry = parent_array[mcid]
    if entry is None:
        return keys
    if isinstance(entry, pikepdf.Array):
        for item in entry:
            if item is not None:
                keys.add(_object_key(item))
        return keys
    keys.add(_object_key(entry))
    return keys


def _overlay_repeat_issues(
    pdf: pikepdf.Pdf,
    ir: DocumentIR,
    scans: list[PageContentScan],
) -> list[Issue]:
    # Detect semantic tags left on earlier overlay pages
    issues: list[Issue] = []
    for element in ir.elements.values():
        if element.mcid is None or len(element.render.pages) < 2:
            continue
        for page_number in element.render.pages[:-1]:
            if page_number < 1 or page_number > len(scans):
                continue
            scan = scans[page_number - 1]
            if element.mcid not in scan.mcid_counts:
                continue
            issues.append(
                Issue(
                    element_id=element.id,
                    code="overlay_repeat_tagged",
                    severity="error",
                    message="An overlay repeat remains semantically tagged",
                    details={"page": page_number, "mcid": element.mcid},
                )
            )
    return issues


def _structure_completeness_issues(
    pdf: pikepdf.Pdf,
    ir: DocumentIR,
    bindings: list[McidBinding],
    page_numbers: dict[tuple[int, int] | tuple[str, int], int],
) -> list[Issue]:
    # Ensure expected marked elements appear on their final page
    issues: list[Issue] = []
    available: dict[tuple[int, int], list[McidBinding]] = {}
    for binding in bindings:
        page_number = page_numbers.get(binding.page_key)
        if page_number is None:
            continue
        key = (page_number, binding.mcid)
        values = available.setdefault(key, [])
        values.append(binding)
    for element in ir.elements.values():
        if element.mcid is None or not element.render.pages:
            continue
        final_page = element.render.pages[-1]
        expected_role = element.accessibility.role
        if element.semantic_type == "list_item":
            expected_role = "LBody"
        matches = available.get((final_page, element.mcid), [])
        role_match = False
        for binding in matches:
            if expected_role is None or binding.role == expected_role:
                role_match = True
                break
        if role_match:
            continue
        issues.append(
            Issue(
                element_id=element.id,
                code="structure_content_missing",
                severity="veto",
                message="Visible marked content is missing from the output structure",
                details={
                    "page": final_page,
                    "mcid": element.mcid,
                    "expected_role": expected_role,
                },
            )
        )
    return issues

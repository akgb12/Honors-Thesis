import re
from dataclasses import dataclass, field
from pathlib import Path

from a11y_pipeline.ir.models import DocumentIR

SCALED_POINTS_PER_POINT = 65536


@dataclass
class AuxData:
    pages_by_key: dict[str, set[int]] = field(default_factory=dict)
    anchors: dict[tuple[str, int], tuple[float, float]] = field(default_factory=dict)
    sizes: dict[tuple[str, int], tuple[float, float, float]] = field(default_factory=dict)


def read_aux(path: Path) -> AuxData:
    # Parse marker pages positions and measured dimensions
    return parse_aux(path.read_text(encoding="utf-8", errors="replace"))


def parse_aux(text: str) -> AuxData:
    # Parse supported marker records from auxiliary text
    data = AuxData()
    position_pattern = re.compile(
        r"\\zref@newlabel\{([^{}]+)@(\d+)\}"
        r"\{[^\n]*?\\posx\{([^{}]+)\}\\posy\{([^{}]+)\}[^\n]*?\}"
    )
    for match in position_pattern.finditer(text):
        key = match.group(1)
        page = int(match.group(2))
        x = _dimension_points(match.group(3), scaled_default=True)
        y = _dimension_points(match.group(4), scaled_default=True)
        data.anchors[(key, page)] = (x, y)
    span_pattern = re.compile(r"\\aelspanpos\{([^{}]+)\}\{(\d+)\}")
    for match in span_pattern.finditer(text):
        _add_page(data, match.group(1), int(match.group(2)))
    size_pattern = re.compile(r"\\aelsize\{([^{}]+)\}\{([^{}]+)\}\{([^{}]+)\}\{([^{}]+)\}\{(\d+)\}")
    for match in size_pattern.finditer(text):
        key = match.group(1)
        page = int(match.group(5))
        width = _dimension_points(match.group(2), scaled_default=False)
        height = _dimension_points(match.group(3), scaled_default=False)
        depth = _dimension_points(match.group(4), scaled_default=False)
        data.sizes[(key, page)] = (width, height, depth)
        _add_page(data, key, page)
    return data


def apply_aux_mapping(ir: DocumentIR, data: AuxData) -> DocumentIR:
    # Return a mapped IR without changing the caller copy
    mapped = ir.model_copy(deep=True)
    for element in mapped.elements.values():
        if element.mcid is None:
            continue
        key = element.id.replace("/", "-")
        pages = sorted(data.pages_by_key.get(key, set()))
        if not pages:
            continue
        last_page = pages[-1]
        element.render.pages = pages
        element.render.anchor = data.anchors.get((key, last_page))
        element.render.mapping_method = "marker"
        element.render.confidence = 0.8
        size = data.sizes.get((key, last_page))
        anchor = element.render.anchor
        if element.semantic_type == "figure" and size is not None and anchor is not None:
            width, height, depth = size
            x, y = anchor
            element.render.bbox = (x, y - depth, x + width, y + height)
            element.render.confidence = 0.95
    _map_container_pages(mapped)
    return mapped


def _add_page(data: AuxData, key: str, page: int) -> None:
    # Add one physical page to a marker key
    pages = data.pages_by_key.setdefault(key, set())
    pages.add(page)


def _dimension_points(value: str, scaled_default: bool) -> float:
    # Convert TeX point dimensions and integer scaled points
    cleaned = value.strip()
    if cleaned.endswith("pt"):
        return float(cleaned[:-2])
    number = float(cleaned)
    if scaled_default:
        return number / SCALED_POINTS_PER_POINT
    return number / SCALED_POINTS_PER_POINT


def _map_container_pages(ir: DocumentIR) -> None:
    # Union element pages with pause based fallback frames
    previous_page = 0
    for container in ir.containers:
        pages: set[int] = set()
        for element_id in container.element_ids:
            _collect_element_pages(ir, element_id, pages)
        if pages:
            container.rendered_pages = sorted(pages)
            previous_page = max(previous_page, container.rendered_pages[-1])
            continue
        page_count = int(container.attrs.get("pauses", 0)) + 1
        container.rendered_pages = []
        for offset in range(page_count):
            container.rendered_pages.append(previous_page + offset + 1)
        previous_page = container.rendered_pages[-1]


def _collect_element_pages(
    ir: DocumentIR,
    element_id: str,
    pages: set[int],
) -> None:
    # Gather mapped pages from one semantic subtree
    element = ir.elements[element_id]
    for page in element.render.pages:
        pages.add(page)
    for child_id in element.child_ids:
        _collect_element_pages(ir, child_id, pages)

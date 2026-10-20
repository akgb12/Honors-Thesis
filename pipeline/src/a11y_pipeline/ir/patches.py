from typing import Any

from a11y_pipeline.ir.models import DocumentIR, Patch


def _set_path(element_data: dict[str, Any], path: str, value: Any) -> None:
    # Set a dotted path in one element mapping
    parts = path.split(".")
    if not path or any(not part for part in parts):
        raise ValueError("patch path must contain field names")
    target: dict[str, Any] = element_data
    for part in parts[:-1]:
        child = target.get(part)
        if not isinstance(child, dict):
            raise ValueError(f"patch path does not resolve through {part}")
        target = child
    target[parts[-1]] = value


def apply_patches(base_ir: DocumentIR, patches: list[Patch]) -> DocumentIR:
    # Apply validated patches without changing the base document
    document_data = base_ir.model_dump(mode="python", round_trip=True)
    elements = document_data["elements"]
    for patch in patches:
        element_data = elements.get(patch.element_id)
        if element_data is None:
            raise ValueError(f"unknown element id {patch.element_id}")
        accessibility = element_data["accessibility"]
        if accessibility["locked"] and patch.by != "human":
            raise ValueError(f"element {patch.element_id} is locked")
        _set_path(element_data, patch.path, patch.value)
    return DocumentIR.model_validate(document_data)

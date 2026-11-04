from pydantic import BaseModel, ConfigDict

from a11y_pipeline.ir.models import DocumentIR


class Task(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    element_id: str
    capability: str
    reason: str


def analyze_needs(document: DocumentIR) -> list[Task]:
    # Find elements that need semantic model work
    tasks: list[Task] = []
    for element in document.elements.values():
        accessibility = element.accessibility
        if element.semantic_type != "figure":
            continue
        if accessibility.status != "needs_description":
            continue
        if accessibility.locked:
            continue
        tasks.append(
            Task(
                element_id=element.id,
                capability="figure_description",
                reason="Figure needs an accessibility description",
            )
        )
    return tasks

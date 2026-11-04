from typing import Any, Literal

from pydantic import Field

from a11y_pipeline.ir.models import StrictModel


class OutputOperation(StrictModel):
    output: Literal["tagged_pdf", "updated_source"]
    operation: str
    element_id: str | None = None
    source_file: str | None = None
    page: int | None = None
    details: dict[str, Any] = Field(default_factory=dict)

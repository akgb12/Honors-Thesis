from dataclasses import dataclass

from pydantic import BaseModel

from a11y_pipeline.ir.models import HistoryEntry, Patch


class FigureDescriptionInput(BaseModel):
    element_id: str
    subtype: str
    image_png: bytes
    source_code: str | None
    visible_labels: list[str]
    slide_title: str | None
    nearby_text: list[str]


class FigureDescriptionOutput(BaseModel):
    alt_text: str
    extended_description: str | None = None
    decorative: bool = False


@dataclass(frozen=True)
class CapabilityResult:
    patches: list[Patch]
    history: HistoryEntry | None

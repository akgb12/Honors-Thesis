from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SemanticType = Literal[
    "document_title",
    "heading",
    "paragraph",
    "list",
    "list_item",
    "formula",
    "figure",
    "table",
    "title_page",
    "unknown",
]
FigureSubtype = Literal["diagram", "image", "chart", "other"]
Method = Literal["deterministic", "model", "human"]
ElementStatus = Literal[
    "done",
    "needs_description",
    "model_generated",
    "needs_review",
    "failed",
    "missing_asset",
    "not_handled",
]
MappingMethod = Literal["marker", "synctex", "position_match", "none"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceRef(StrictModel):
    file: str
    line_start: int
    line_end: int
    char_start: int
    char_end: int
    native_type: str
    raw: str | None = None


class RenderRef(StrictModel):
    pages: list[int] = Field(default_factory=list)
    bbox: tuple[float, float, float, float] | None = None
    anchor: tuple[float, float] | None = None
    mapping_method: MappingMethod = "none"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class Classification(StrictModel):
    method: Method = "deterministic"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)


class Accessibility(StrictModel):
    role: str | None = None
    decorative: bool = False
    decorative_suggested: bool = False
    alt_text: str | None = None
    extended_description: str | None = None
    status: ElementStatus = "done"
    locked: bool = False


class Fidelity(StrictModel):
    must_preserve: bool = True
    signature: str | None = None
    required_concepts: list[str] = Field(default_factory=list)
    excluded_concepts: list[str] = Field(default_factory=list)


class HistoryEntry(StrictModel):
    run_id: str
    round: int
    change: str
    by: Method
    model: str | None = None
    prompt_version: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


class Element(StrictModel):
    id: str
    semantic_type: SemanticType
    subtype: str | None = None
    parent_id: str | None = None
    child_ids: list[str] = Field(default_factory=list)
    content: dict[str, Any] = Field(default_factory=dict)
    attrs: dict[str, Any] = Field(default_factory=dict)
    fingerprint: str
    source: SourceRef
    render: RenderRef = Field(default_factory=RenderRef)
    classification: Classification = Field(default_factory=Classification)
    accessibility: Accessibility = Field(default_factory=Accessibility)
    fidelity: Fidelity = Field(default_factory=Fidelity)
    history: list[HistoryEntry] = Field(default_factory=list)
    mcid: int | None = None


class Container(StrictModel):
    id: str
    kind: Literal["slide", "page", "section"]
    title_element_id: str | None = None
    element_ids: list[str] = Field(default_factory=list)
    rendered_pages: list[int] = Field(default_factory=list)
    attrs: dict[str, Any] = Field(default_factory=dict)


class Asset(StrictModel):
    id: str
    referenced_as: str
    resolved_path: str | None
    status: Literal["found", "missing", "ambiguous"]
    origin: Literal["external_file", "embedded"]
    sha256: str | None = None
    used_by: list[str] = Field(default_factory=list)


class Issue(StrictModel):
    element_id: str | None
    code: str
    severity: Literal["info", "warning", "error", "veto"]
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class DocumentIR(StrictModel):
    schema_version: Literal["1"] = "1"
    document_id: str
    source_format: Literal["tex-beamer"]
    main_file: str
    metadata: dict[str, str] = Field(default_factory=dict)
    containers: list[Container]
    elements: dict[str, Element]
    assets: dict[str, Asset] = Field(default_factory=dict)
    issues: list[Issue] = Field(default_factory=list)


class Patch(StrictModel):
    element_id: str
    path: str
    value: Any
    by: Method
    round: int
    note: str = ""


class Candidate(StrictModel):
    candidate_id: str
    round: int
    patches: list[Patch]
    pdf_path: str | None = None
    scores: dict[str, float] = Field(default_factory=dict)
    vetoes: list[Issue] = Field(default_factory=list)
    issues: list[Issue] = Field(default_factory=list)

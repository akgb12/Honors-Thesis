from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class NativeSource:
    file: str
    line_start: int
    line_end: int
    char_start: int
    char_end: int
    native_type: str
    raw: str


@dataclass
class NativeRecord:
    kind: str
    source: NativeSource
    text: str | None = None
    attrs: dict[str, Any] = field(default_factory=dict)
    children: list["NativeRecord"] = field(default_factory=list)


@dataclass
class NativeDocument:
    source_file: str
    source_text: str
    metadata: dict[str, str] = field(default_factory=dict)
    metadata_sources: dict[str, NativeSource] = field(default_factory=dict)
    records: list[NativeRecord] = field(default_factory=list)
    user_macros: list[str] = field(default_factory=list)
    hypersetup: dict[str, str] = field(default_factory=dict)

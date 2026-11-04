import hashlib
from dataclasses import dataclass, field

from a11y_pipeline.ir.models import SemanticType


def _strip_tex_comments(text: str) -> str:
    # Remove comments while preserving escaped percent signs
    cleaned_lines: list[str] = []
    for line in text.splitlines():
        cleaned: list[str] = []
        for index, character in enumerate(line):
            if character == "%":
                backslash_count = 0
                previous = index - 1
                while previous >= 0 and line[previous] == "\\":
                    backslash_count += 1
                    previous -= 1
                if backslash_count % 2 == 0:
                    break
            cleaned.append(character)
        cleaned_lines.append("".join(cleaned))
    return "\n".join(cleaned_lines)


def normalize_source(text: str) -> str:
    # Normalize source for stable content matching
    without_comments = _strip_tex_comments(text)
    return " ".join(without_comments.split())


def fingerprint_source(text: str) -> str:
    # Create the short source fingerprint
    normalized = normalize_source(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def container_id(index: int) -> str:
    # Format a one based container identifier
    if index < 1:
        raise ValueError("container index must be at least 1")
    return f"slide_{index:02d}"


@dataclass
class IdAllocator:
    _counts: dict[tuple[str, str], int] = field(default_factory=dict)

    def allocate(self, parent_id: str, semantic_type: SemanticType) -> str:
        # Allocate the next identifier within a parent and type
        if not parent_id:
            raise ValueError("parent id cannot be empty")
        key = (parent_id, semantic_type)
        next_index = self._counts.get(key, 0) + 1
        self._counts[key] = next_index
        return f"{parent_id}/{semantic_type}_{next_index:02d}"

import json
from pathlib import Path

from a11y_pipeline.ir.models import DocumentIR


def dumps_document(document: DocumentIR) -> str:
    # Serialize a document with stable formatting
    data = document.model_dump(mode="json")
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def loads_document(text: str) -> DocumentIR:
    # Validate a document from JSON text
    return DocumentIR.model_validate_json(text)


def write_document(document: DocumentIR, path: Path) -> None:
    # Write a stable document snapshot
    path.write_text(dumps_document(document), encoding="utf-8")


def read_document(path: Path) -> DocumentIR:
    # Read and validate a document snapshot
    return loads_document(path.read_text(encoding="utf-8"))

import hashlib
import json
import platform
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from a11y_pipeline.bundle.bundle import Bundle
from a11y_pipeline.orchestration.state import RunState
from a11y_pipeline.telemetry import redact_secret_fields


def telemetry_totals(path: Path) -> dict[str, int | float]:
    # Total safe model usage from completed telemetry lines
    totals: dict[str, int | float] = {
        "calls": 0,
        "errors": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_usd": 0.0,
    }
    if not path.is_file():
        return totals
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        totals["calls"] += 1
        if event.get("status") == "error":
            totals["errors"] += 1
        totals["input_tokens"] += _number(event.get("input_tokens"), int)
        totals["output_tokens"] += _number(event.get("output_tokens"), int)
        totals["cost_usd"] += _number(event.get("cost_usd"), float)
    return totals


def build_manifest(
    state: RunState,
    bundle: Bundle,
    input_path: Path,
    prompt_versions: list[str],
    pages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    # Build the complete redacted run manifest
    files: list[dict[str, Any]] = []
    total_input_bytes = 0
    for relative in bundle.files:
        path = bundle.root / relative
        size = path.stat().st_size
        total_input_bytes += size
        files.append(
            {
                "path": relative,
                "bytes": size,
                "sha256": _sha256(path),
            }
        )
    totals = telemetry_totals(state.telemetry_path)
    totals["input_files"] = len(files)
    totals["input_bytes"] = total_input_bytes
    totals["candidates"] = len(state.candidates)
    totals["issues"] = len(state.issues)
    manifest = {
        "run_id": state.run_id,
        "inputs": {
            "source": str(input_path.expanduser().resolve()),
            "main_file": bundle.main_file,
            "files": files,
        },
        "versions": {
            "python": platform.python_version(),
            "a11y_pipeline": _package_version(),
            "schema": state.base_ir.schema_version if state.base_ir is not None else None,
        },
        "effort": state.effort,
        "model": {
            "provider": state.config.model_provider,
            "name": state.config.generator_model,
        },
        "prompt_versions": prompt_versions,
        "stop_reason": state.stop_reason,
        "selected_candidate_id": state.selected_candidate_id,
        "totals": totals,
        "pages": pages or [],
    }
    safe = redact_secret_fields(manifest)
    if not isinstance(safe, dict):
        raise TypeError("Redacted manifest must remain an object")
    return safe


def write_manifest(path: Path, manifest: dict[str, Any]) -> Path:
    # Write stable redacted manifest JSON
    safe = redact_secret_fields(manifest)
    text = json.dumps(safe, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _sha256(path: Path) -> str:
    # Hash one input file without loading it fully
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while True:
            block = source.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _package_version() -> str:
    # Read the installed pipeline package version
    try:
        return version("a11y-pipeline")
    except PackageNotFoundError:
        return "0.1.0"


def _number(value: object, kind: type[int] | type[float]) -> int | float:
    # Convert telemetry numbers while ignoring redacted values
    if isinstance(value, bool):
        return kind()
    if isinstance(value, (int, float)):
        return kind(value)
    return kind()

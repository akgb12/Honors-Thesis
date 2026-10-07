import json
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from a11y_pipeline.ir.serialize import write_document
from a11y_pipeline.orchestration.state import RunState

RUN_ID_PATTERN = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{8}$")


@dataclass(frozen=True)
class RunFolder:
    root: Path

    @property
    def run_id(self) -> str:
        # Return the timestamped run identifier
        return self.root.name

    @property
    def manifest_path(self) -> Path:
        # Return the manifest output path
        return self.root / "manifest.json"

    @property
    def telemetry_path(self) -> Path:
        # Return the telemetry output path
        return self.root / "telemetry.jsonl"

    @property
    def output_dir(self) -> Path:
        # Return the final output directory
        return self.root / "output"

    @property
    def report_path(self) -> Path:
        # Return the HTML report output path
        return self.root / "report.html"


def create_run_folder(
    output_root: Path,
    *,
    timestamp: datetime | None = None,
    short_id: str | None = None,
) -> RunFolder:
    # Create the complete fixed run directory layout
    moment = timestamp or datetime.now().astimezone()
    identifier = short_id or uuid4().hex[:8]
    run_id = moment.strftime("%Y%m%d-%H%M%S") + "-" + identifier
    if RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise ValueError("Run identifier must use timestamp and eight lowercase hex characters")
    root = output_root.expanduser().resolve() / run_id
    root.mkdir(parents=True, exist_ok=False)
    directories = [
        root / "candidates",
        root / "work",
        root / "pages",
        root / "crops",
        root / "output",
    ]
    for directory in directories:
        directory.mkdir()
    return RunFolder(root=root)


def write_run_snapshots(folder: RunFolder, state: RunState) -> None:
    # Write stable base candidate and final snapshots
    if state.base_ir is None:
        raise ValueError("A completed run must have a base IR")
    if state.final_ir is None:
        raise ValueError("A completed run must have a final IR")
    write_document(state.base_ir, folder.root / "ir_base.json")
    write_document(state.final_ir, folder.root / "ir_final.json")
    for candidate in state.candidates:
        path = folder.root / "candidates" / f"{candidate.candidate_id}.json"
        payload = candidate.model_dump(mode="json")
        text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        path.write_text(text, encoding="utf-8")


def archive_project(project_root: Path, output_path: Path) -> Path:
    # Create a stable source project zip
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        files: list[Path] = []
        for path in project_root.rglob("*"):
            if path.is_file():
                files.append(path)
        files.sort()
        for path in files:
            relative = path.relative_to(project_root).as_posix()
            archive.write(path, relative)
    return output_path

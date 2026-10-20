import json
import re
import zipfile
from datetime import datetime
from pathlib import Path

from a11y_pipeline.bundle.bundle import Bundle
from a11y_pipeline.config import Settings
from a11y_pipeline.ir.ids import fingerprint_source
from a11y_pipeline.ir.models import (
    Accessibility,
    Candidate,
    Container,
    DocumentIR,
    Element,
    SourceRef,
)
from a11y_pipeline.orchestration.state import RunState
from a11y_pipeline.runs.folder import archive_project, create_run_folder, write_run_snapshots
from a11y_pipeline.runs.manifest import build_manifest, write_manifest
from a11y_pipeline.telemetry import REDACTED


def test_run_folder_uses_timestamp_short_id_and_fixed_layout(tmp_path: Path) -> None:
    # Create the exact M12 run layout
    folder = create_run_folder(
        tmp_path,
        timestamp=datetime(2026, 10, 7, 1, 2, 3),
        short_id="12ab34cd",
    )

    assert folder.run_id == "20261007-010203-12ab34cd"
    assert re.fullmatch(r"\d{8}-\d{6}-[0-9a-f]{8}", folder.run_id)
    for relative in ["candidates", "work", "pages", "crops", "output"]:
        assert (folder.root / relative).is_dir()


def test_snapshots_archive_and_manifest_are_complete_and_redacted(tmp_path: Path) -> None:
    # Write every stable run record without credential values
    project = tmp_path / "project"
    project.mkdir()
    (project / "main.tex").write_text(
        "\\documentclass{beamer}\\begin{document}\\end{document}",
        encoding="utf-8",
    )
    bundle = Bundle.from_path(project)
    folder = create_run_folder(
        tmp_path / "runs",
        timestamp=datetime(2026, 10, 7, 1, 2, 3),
        short_id="abcdef12",
    )
    document = _document()
    telemetry = folder.telemetry_path
    telemetry.write_text(
        '{"cost_usd":0.25,"input_tokens":12,"output_tokens":8,"status":"ok"}\n',
        encoding="utf-8",
    )
    state = RunState(
        run_id=folder.run_id,
        config=Settings(_env_file=None, model_provider="fake"),
        effort="medium",
        bundle=bundle,
        base_ir=document,
        final_ir=document,
        candidates=[Candidate(candidate_id="c0", round=0, patches=[])],
        telemetry_path=telemetry,
        stop_reason="nothing_failing",
        selected_candidate_id="c0",
    )

    write_run_snapshots(folder, state)
    archive_project(project, folder.output_dir / "updated_project.zip")
    manifest = build_manifest(state, bundle, project, ["figure_description_v1"])
    manifest["api_key"] = "must disappear"
    manifest["nested"] = {"password_hint": "must disappear"}
    write_manifest(folder.manifest_path, manifest)

    stored = json.loads(folder.manifest_path.read_text(encoding="utf-8"))
    assert stored["api_key"] == REDACTED
    assert stored["nested"]["password_hint"] == REDACTED
    assert stored["totals"]["input_tokens"] == 12
    assert stored["totals"]["output_tokens"] == 8
    assert stored["totals"]["cost_usd"] == 0.25
    assert (folder.root / "ir_base.json").is_file()
    assert (folder.root / "ir_final.json").is_file()
    assert (folder.root / "candidates" / "c0.json").is_file()
    with zipfile.ZipFile(folder.output_dir / "updated_project.zip") as archive:
        assert archive.namelist() == ["main.tex"]


def _document() -> DocumentIR:
    # Build one minimal run snapshot document
    raw = "Title"
    heading = Element(
        id="slide_01/heading_01",
        semantic_type="heading",
        parent_id="slide_01",
        content={"text": raw},
        fingerprint=fingerprint_source(raw),
        source=SourceRef(
            file="main.tex",
            line_start=1,
            line_end=1,
            char_start=0,
            char_end=len(raw),
            native_type="frame title",
            raw=raw,
        ),
        accessibility=Accessibility(role="H2"),
    )
    return DocumentIR(
        document_id="runfolder123456",
        source_format="tex-beamer",
        main_file="main.tex",
        containers=[
            Container(
                id="slide_01",
                kind="slide",
                title_element_id=heading.id,
                element_ids=[heading.id],
            )
        ],
        elements={heading.id: heading},
    )

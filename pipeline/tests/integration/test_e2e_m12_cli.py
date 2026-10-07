import json
import zipfile
from pathlib import Path

import pytest

from a11y_pipeline.cli import main
from a11y_pipeline.evaluation.pdf_checks import check_pdf
from a11y_pipeline.ir.serialize import read_document

PIPELINE_ROOT = Path(__file__).parents[2]


@pytest.mark.tex
@pytest.mark.slow
def test_a11y_run_materializes_every_m12_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Run the complete lecture fixture with one seeded repair
    monkeypatch.chdir(PIPELINE_ROOT)
    monkeypatch.setenv("MODEL_PROVIDER", "fake")
    output_root = tmp_path / "runs"

    result = main(
        [
            "run",
            "tests/fixtures/lecture_sample",
            "--effort",
            "medium",
            "--seed-weak",
            "slide_04/figure_01",
            "--out",
            str(output_root),
        ]
    )

    assert result == 0
    folders: list[Path] = []
    for path in output_root.iterdir():
        if path.is_dir():
            folders.append(path)
    assert len(folders) == 1
    run_root = folders[0]
    required_files = [
        "manifest.json",
        "ir_base.json",
        "ir_final.json",
        "telemetry.jsonl",
        "output/tagged.pdf",
        "output/updated_project.zip",
        "output/changes.diff",
        "report.html",
    ]
    for relative in required_files:
        assert (run_root / relative).is_file(), relative
    for relative in ["work", "pages", "crops", "output/updated_project", "candidates"]:
        assert (run_root / relative).is_dir(), relative
    for candidate_id in ["c0", "c1", "c2"]:
        assert (run_root / "candidates" / f"{candidate_id}.json").is_file()

    page_images = list((run_root / "pages").glob("*.png"))
    crop_images = list((run_root / "crops").glob("*.png"))
    assert len(page_images) == 10
    assert len(crop_images) == 2
    assert (run_root / "work" / "original" / "latexmk_output.log").is_file()
    assert (run_root / "work" / "marked" / "latexmk_output.log").is_file()
    assert (run_root / "work" / "updated_verify" / "latexmk_output.log").is_file()

    final_ir = read_document(run_root / "ir_final.json")
    repaired = final_ir.elements["slide_04/figure_01"]
    regression = final_ir.elements["slide_03/figure_01"]
    assert repaired.accessibility.status == "model_generated"
    assert "Five-fold cross-validation" in (repaired.accessibility.alt_text or "")
    assert repaired.accessibility.alt_text != "Five boxes in a row, one is blue."
    assert regression.accessibility.status == "model_generated"
    assert regression.accessibility.alt_text

    events: list[dict[str, object]] = []
    for line in (run_root / "telemetry.jsonl").read_text(encoding="utf-8").splitlines():
        events.append(json.loads(line))
    assert len(events) == 2
    requested_ids: list[object] = []
    for event in events:
        requested_ids.append(event["element_id"])
    assert requested_ids == ["slide_03/figure_01", "slide_04/figure_01"]

    manifest = json.loads((run_root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["effort"] == "medium"
    assert manifest["stop_reason"] == "nothing_failing"
    assert manifest["selected_candidate_id"] == "c2"
    assert manifest["model"]["provider"] == "fake"
    assert manifest["totals"]["candidates"] == 3
    assert manifest["totals"]["input_tokens"] == 24
    assert manifest["totals"]["output_tokens"] == 16

    tagged = run_root / "output" / "tagged.pdf"
    checks = check_pdf(tagged, final_ir)
    assert checks.passed
    diff = (run_root / "output" / "changes.diff").read_text(encoding="utf-8")
    assert r"\hypersetup" in diff
    assert "alt={" in diff
    assert "% a11y-alt:" in diff
    report = (run_root / "report.html").read_text(encoding="utf-8")
    assert "Preliminary A" in report
    assert "Candidate round history" in report
    assert "Not handled" in report
    assert "page-stage" in report
    with zipfile.ZipFile(run_root / "output" / "updated_project.zip") as archive:
        names = archive.namelist()
    assert "main.tex" in names
    assert "figs/regression.png" in names

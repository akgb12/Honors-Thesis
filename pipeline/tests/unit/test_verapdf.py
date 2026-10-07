import subprocess
from pathlib import Path

from a11y_pipeline.evaluation import verapdf


def test_verapdf_is_not_run_without_configuration(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # Skip optional validation when no executable is configured
    monkeypatch.delenv("VERAPDF_PATH", raising=False)

    result = verapdf.run_verapdf(tmp_path / "document.pdf")

    assert not result.ran
    assert result.passed is None
    assert result.pass_rate is None
    assert result.message == "veraPDF not run because VERAPDF_PATH is not set"


def test_verapdf_uses_ua1_json_and_reports_rule_rate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # Parse configured veraPDF validation results
    calls: list[list[str]] = []

    def fake_run(command, capture_output, check, text):
        # Capture one optional checker command
        calls.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=('{"report":{"isCompliant":false,"passedRules":8,"failedRules":2}}'),
            stderr="",
        )

    monkeypatch.setattr(verapdf.subprocess, "run", fake_run)
    executable = tmp_path / "verapdf"
    pdf_path = tmp_path / "document.pdf"

    result = verapdf.run_verapdf(pdf_path, executable)

    assert calls == [
        [
            str(executable),
            "--format",
            "json",
            "--flavour",
            "ua1",
            str(pdf_path),
        ]
    ]
    assert result.ran
    assert not result.passed
    assert result.pass_rate == 80.0

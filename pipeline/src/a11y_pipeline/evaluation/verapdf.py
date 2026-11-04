import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class VeraPdfResult:
    ran: bool
    passed: bool | None
    pass_rate: float | None
    data: dict[str, Any] | None
    message: str


def run_verapdf(
    pdf_path: Path,
    executable: Path | None = None,
) -> VeraPdfResult:
    # Run veraPDF only when an executable is configured
    selected = executable
    if selected is None:
        configured = os.environ.get("VERAPDF_PATH", "").strip()
        if configured:
            selected = Path(configured)
    if selected is None:
        return VeraPdfResult(
            ran=False,
            passed=None,
            pass_rate=None,
            data=None,
            message="veraPDF not run because VERAPDF_PATH is not set",
        )
    try:
        completed = subprocess.run(
            [
                str(selected),
                "--format",
                "json",
                "--flavour",
                "ua1",
                str(pdf_path),
            ],
            capture_output=True,
            check=False,
            text=True,
        )
    except OSError as error:
        return VeraPdfResult(
            ran=True,
            passed=False,
            pass_rate=None,
            data=None,
            message=f"veraPDF could not start: {error}",
        )
    output = completed.stdout.strip()
    try:
        parsed = json.loads(output)
    except json.JSONDecodeError:
        detail = completed.stderr.strip() or output or "No output"
        return VeraPdfResult(
            ran=True,
            passed=False,
            pass_rate=None,
            data=None,
            message=f"veraPDF returned invalid JSON: {detail}",
        )
    data: dict[str, Any] = {}
    if isinstance(parsed, dict):
        data = parsed
    passed, pass_rate = _validation_summary(data, completed.returncode)
    return VeraPdfResult(
        ran=True,
        passed=passed,
        pass_rate=pass_rate,
        data=data,
        message="veraPDF completed",
    )


def _validation_summary(
    data: dict[str, Any],
    return_code: int,
) -> tuple[bool, float | None]:
    # Derive compliance and pass rate from common veraPDF fields
    counts = _find_rule_counts(data)
    pass_rate = None
    if counts is not None:
        passed_count, failed_count = counts
        total = passed_count + failed_count
        if total > 0:
            pass_rate = passed_count / total * 100.0
    compliant = _find_boolean(data, "isCompliant")
    if compliant is None:
        compliant = return_code == 0
        if counts is not None and counts[1] > 0:
            compliant = False
    return compliant, pass_rate


def _find_rule_counts(value: Any) -> tuple[int, int] | None:
    # Find one paired passed and failed rule count
    if isinstance(value, dict):
        pairs = (
            ("passedRules", "failedRules"),
            ("passedChecks", "failedChecks"),
        )
        for passed_key, failed_key in pairs:
            if passed_key in value and failed_key in value:
                passed = _count_value(value[passed_key])
                failed = _count_value(value[failed_key])
                if passed is not None and failed is not None:
                    return passed, failed
        for child in value.values():
            found = _find_rule_counts(child)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_rule_counts(child)
            if found is not None:
                return found
    return None


def _count_value(value: Any) -> int | None:
    # Convert a count or collection into a count
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, list):
        return len(value)
    return None


def _find_boolean(value: Any, key: str) -> bool | None:
    # Find a named Boolean recursively
    if isinstance(value, dict):
        candidate = value.get(key)
        if isinstance(candidate, bool):
            return candidate
        for child in value.values():
            found = _find_boolean(child, key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_boolean(child, key)
            if found is not None:
                return found
    return None

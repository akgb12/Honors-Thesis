import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pikepdf


@dataclass(frozen=True)
class CompileResult:
    pdf_path: Path
    aux_path: Path
    log_path: Path
    page_count: int
    errors: int


class CompileError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        source_file: str,
        line: int | None,
        tex_error: str | None,
        log_path: Path,
    ):
        # Store the first actionable TeX failure
        super().__init__(message)
        self.source_file = source_file
        self.line = line
        self.tex_error = tex_error
        self.log_path = log_path


def compile_project(
    project_root: Path,
    main_file: str,
    timeout_seconds: int = 180,
) -> CompileResult:
    # Compile one isolated project with pdfLaTeX through latexmk
    root = project_root.resolve()
    main_path = root / main_file
    if not main_path.is_file():
        raise FileNotFoundError(f"Main TeX file does not exist: {main_file}")
    command = [
        "latexmk",
        "-pdf",
        "-interaction=nonstopmode",
        "-halt-on-error",
        "-file-line-error",
        main_file,
    ]
    output_path = root / "latexmk_output.log"
    try:
        completed = subprocess.run(
            command,
            cwd=root,
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout_seconds,
        )
        output = completed.stdout + completed.stderr
    except subprocess.TimeoutExpired as error:
        output = _timeout_output(error)
        output_path.write_text(output, encoding="utf-8")
        raise CompileError(
            f"TeX compilation timed out after {timeout_seconds} seconds",
            source_file=main_file,
            line=None,
            tex_error=None,
            log_path=output_path,
        ) from error
    output_path.write_text(output, encoding="utf-8")
    tex_log = main_path.with_suffix(".log")
    error_source = output
    if tex_log.is_file():
        error_source = tex_log.read_text(encoding="utf-8", errors="replace")
    if completed.returncode != 0:
        tex_error, line = _first_tex_error(error_source)
        location = main_file
        if line is not None:
            location = f"{main_file}:{line}"
        detail = tex_error or "latexmk failed without a TeX error line"
        raise CompileError(
            f"{location}: {detail}",
            source_file=main_file,
            line=line,
            tex_error=tex_error,
            log_path=output_path,
        )
    pdf_path = main_path.with_suffix(".pdf")
    aux_path = main_path.with_suffix(".aux")
    if not pdf_path.is_file() or not aux_path.is_file():
        raise CompileError(
            f"{main_file}: latexmk completed without expected PDF or AUX output",
            source_file=main_file,
            line=None,
            tex_error=None,
            log_path=output_path,
        )
    with pikepdf.open(pdf_path) as pdf:
        page_count = len(pdf.pages)
    return CompileResult(
        pdf_path=pdf_path,
        aux_path=aux_path,
        log_path=output_path,
        page_count=page_count,
        errors=0,
    )


def _timeout_output(error: subprocess.TimeoutExpired) -> str:
    # Combine available process output after a timeout
    output = ""
    if error.stdout is not None:
        if isinstance(error.stdout, bytes):
            output += error.stdout.decode("utf-8", errors="replace")
        else:
            output += error.stdout
    if error.stderr is not None:
        if isinstance(error.stderr, bytes):
            output += error.stderr.decode("utf-8", errors="replace")
        else:
            output += error.stderr
    return output


def _first_tex_error(log_text: str) -> tuple[str | None, int | None]:
    # Extract the first TeX bang error and nearby source line
    match = re.search(r"^!\s*(.+)$", log_text, re.MULTILINE)
    if match is None:
        file_error = re.search(r"^[^:\n]+\.tex:(\d+):\s*(.+)$", log_text, re.MULTILINE)
        if file_error is None:
            return None, None
        return file_error.group(2).strip(), int(file_error.group(1))
    line_match = re.search(r"^l\.(\d+)\b", log_text[match.end() :], re.MULTILINE)
    line = None
    if line_match is not None:
        line = int(line_match.group(1))
    return match.group(1).strip(), line

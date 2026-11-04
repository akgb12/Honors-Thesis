import shutil
from pathlib import Path

from a11y_pipeline.adapters.tex_beamer.preflight import PreflightResult, preflight
from a11y_pipeline.bundle.bundle import Bundle

FIXTURES = Path(__file__).parents[1] / "fixtures"


def _write(path: Path, content: str | bytes = "") -> None:
    # Create a dependency file and any parent folders
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")


def _scan_project(root: Path) -> PreflightResult:
    # Build and scan one test project
    return preflight(Bundle.from_path(root))


def _issue_codes(result: PreflightResult) -> list[str]:
    # Collect issue codes without changing their order
    codes: list[str] = []
    for issue in result.issues:
        codes.append(issue.code)
    return codes


def test_preflight_finds_all_lecture_sample_dependencies() -> None:
    # Verify the complete lecture fixture is runnable
    result = _scan_project(FIXTURES / "lecture_sample")

    assert result.ok
    assert result.missing_images == []
    assert result.missing_critical == []
    assert "figs/regression.png" in result.assets
    assert result.issues == []


def test_preflight_allows_lecture_sample_with_missing_image(tmp_path: Path) -> None:
    # Keep the project runnable when only its raster image is absent
    project = tmp_path / "lecture_sample"
    shutil.copytree(FIXTURES / "lecture_sample", project)
    shutil.rmtree(project / "figs")

    result = _scan_project(project)

    assert result.ok
    assert result.missing_images == ["figs/regression"]
    assert result.missing_critical == []
    assert _issue_codes(result) == ["missing_image"]


def test_preflight_blocks_missing_input_with_source_location(tmp_path: Path) -> None:
    # Block a project whose included source is missing
    _write(tmp_path / "beamer.cls")
    _write(
        tmp_path / "main.tex",
        "\\documentclass{beamer}\n\\begin{document}\n\\input{sections/missing}\n\\end{document}\n",
    )

    result = _scan_project(tmp_path)

    assert not result.ok
    assert result.missing_images == []
    assert result.missing_critical == ["sections/missing"]
    assert _issue_codes(result) == ["missing_input"]
    assert result.issues[0].source_file == "main.tex"
    assert result.issues[0].line == 3


def test_preflight_resolves_every_dependency_category(tmp_path: Path) -> None:
    # Resolve source style theme bibliography image and plot dependencies
    main_source = r"""
\documentclass{beamer}
\graphicspath{{images/}{alternate/}}
\usepackage{localpkg}
\usetheme{Course}
\usecolortheme{Course}
\usefonttheme{Course}
\useinnertheme{Course}
\useoutertheme{Course}
\input{sections/intro}
\include{chapters/details}
\bibliography{refs,more}
\begin{document}
\includegraphics{chart}
\includegraphics{logo.jpeg}
\addplot table [x=epoch,y=score] {data/points.csv};
\end{document}
"""
    _write(tmp_path / "main.tex", main_source)
    _write(tmp_path / "beamer.cls")
    _write(tmp_path / "localpkg.sty", "\\input{styles/shared}\n")
    _write(tmp_path / "styles/shared.tex", "Shared style\n")
    _write(tmp_path / "beamerthemeCourse.sty")
    _write(tmp_path / "beamercolorthemeCourse.sty")
    _write(tmp_path / "beamerfontthemeCourse.sty")
    _write(tmp_path / "beamerinnerthemeCourse.sty")
    _write(tmp_path / "beamerouterthemeCourse.sty")
    _write(tmp_path / "sections/intro.tex", "Introduction\n")
    _write(tmp_path / "chapters/details.tex", "Details\n")
    _write(tmp_path / "refs.bib", "@book{one,title={One}}\n")
    _write(tmp_path / "more.bib", "@book{two,title={Two}}\n")
    _write(tmp_path / "images/chart.png", b"chart")
    _write(tmp_path / "alternate/logo.jpeg", b"logo")
    _write(tmp_path / "data/points.csv", "epoch,score\n1,2\n")

    result = _scan_project(tmp_path)

    assert result.ok
    assert result.missing_images == []
    assert result.missing_critical == []
    assert result.issues == []
    expected_assets = {
        "alternate/logo.jpeg",
        "beamer.cls",
        "beamercolorthemeCourse.sty",
        "beamerfontthemeCourse.sty",
        "beamerinnerthemeCourse.sty",
        "beamerouterthemeCourse.sty",
        "beamerthemeCourse.sty",
        "chapters/details.tex",
        "data/points.csv",
        "images/chart.png",
        "localpkg.sty",
        "more.bib",
        "refs.bib",
        "sections/intro.tex",
        "styles/shared.tex",
    }
    assert set(result.assets) == expected_assets


def test_preflight_reports_images_separately_from_critical_files(tmp_path: Path) -> None:
    # Separate recoverable image gaps from compile blockers
    _write(tmp_path / "beamer.cls")
    _write(
        tmp_path / "main.tex",
        "\\documentclass{beamer}\n"
        "\\begin{document}\n"
        "\\includegraphics{missing-figure}\n"
        "\\bibliography{missing-references}\n"
        "\\addplot table {missing-data.csv};\n"
        "\\end{document}\n",
    )

    result = _scan_project(tmp_path)

    assert not result.ok
    assert result.missing_images == ["missing-figure"]
    assert result.missing_critical == ["missing-data.csv", "missing-references"]
    assert _issue_codes(result) == [
        "missing_image",
        "missing_bibliography",
        "missing_plot_data",
    ]


def test_preflight_rejects_unsupported_engines(tmp_path: Path) -> None:
    # Reject packages that require a non pdfLaTeX engine
    _write(tmp_path / "beamer.cls")
    _write(tmp_path / "fontspec.sty")
    _write(tmp_path / "unicode-math.sty")
    _write(
        tmp_path / "main.tex",
        "\\documentclass{beamer}\n"
        "\\usepackage{fontspec,unicode-math}\n"
        "\\begin{document}Text\\end{document}\n",
    )

    result = _scan_project(tmp_path)

    assert not result.ok
    assert result.missing_critical == []
    assert _issue_codes(result) == ["engine_unsupported", "engine_unsupported"]
    assert result.issues[0].severity == "critical"
    assert result.issues[1].severity == "critical"


def test_preflight_ignores_commented_dependencies(tmp_path: Path) -> None:
    # Ignore macros that appear only inside TeX comments
    _write(tmp_path / "beamer.cls")
    _write(
        tmp_path / "main.tex",
        "\\documentclass{beamer}\n"
        "% \\input{missing}\n"
        "\\begin{document}\n"
        "% \\includegraphics{missing-image}\n"
        "Text\n"
        "\\end{document}\n",
    )

    result = _scan_project(tmp_path)

    assert result.ok
    assert result.missing_images == []
    assert result.missing_critical == []
    assert result.issues == []


def test_preflight_ignores_text_after_end_document(tmp_path: Path) -> None:
    # LaTeX never reads past the end of the document, so neither does pre-flight
    _write(tmp_path / "beamer.cls")
    _write(
        tmp_path / "main.tex",
        "\\documentclass{beamer}\n"
        "\\begin{document}\n"
        "Text\n"
        "\\end{document}\n"
        "Notes pasted later:\n"
        "\\includegraphics[width=...]{...}\n"
        "\\input{missing}\n",
    )

    result = _scan_project(tmp_path)

    assert result.ok
    assert result.missing_images == []
    assert result.missing_critical == []


def test_preflight_still_scans_after_a_commented_end_document(tmp_path: Path) -> None:
    # A commented-out end of document does not stop the scan
    _write(tmp_path / "beamer.cls")
    _write(
        tmp_path / "main.tex",
        "\\documentclass{beamer}\n"
        "\\begin{document}\n"
        "% \\end{document}\n"
        "\\includegraphics{real-missing}\n"
        "\\end{document}\n",
    )

    assert _scan_project(tmp_path).missing_images == ["real-missing"]

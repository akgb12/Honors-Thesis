import shutil
import zipfile
from pathlib import Path

import pytest

from a11y_pipeline.bundle.bundle import Bundle, BundlePathError
from a11y_pipeline.bundle.mainfile import (
    MainFileNotFoundError,
    MultipleMainFilesError,
    find_main_file,
    is_beamer_main_file,
)

BEAMER_SOURCE = r"""
\documentclass[aspectratio=169]{beamer}
\begin{document}
\begin{frame}{Example}
Content
\end{frame}
\end{document}
"""


def _write_zip(path: Path, files: dict[str, str]) -> None:
    # Create a source archive for bundle tests
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)


def test_is_beamer_main_file_requires_class_and_document(tmp_path: Path) -> None:
    # Recognize only complete Beamer entry points
    main = tmp_path / "main.tex"
    main.write_text(BEAMER_SOURCE, encoding="utf-8")
    assert is_beamer_main_file(main)

    article = tmp_path / "article.tex"
    article.write_text(
        "\\documentclass{article}\\begin{document}Text\\end{document}",
        encoding="utf-8",
    )
    assert not is_beamer_main_file(article)

    preamble = tmp_path / "preamble.tex"
    preamble.write_text("\\documentclass{beamer}", encoding="utf-8")
    assert not is_beamer_main_file(preamble)

    commented = tmp_path / "commented.tex"
    commented.write_text(
        "% \\documentclass{beamer}\n% \\begin{document}\n",
        encoding="utf-8",
    )
    assert not is_beamer_main_file(commented)


def test_find_main_file_returns_relative_nested_path(tmp_path: Path) -> None:
    # Find one entry point below the bundle root
    project = tmp_path / "project"
    project.mkdir()
    nested = project / "slides"
    nested.mkdir()
    (nested / "deck.tex").write_text(BEAMER_SOURCE, encoding="utf-8")
    (project / "chapter.tex").write_text("Chapter content", encoding="utf-8")

    assert find_main_file(project) == "slides/deck.tex"


def test_find_main_file_rejects_missing_candidate(tmp_path: Path) -> None:
    # Report when a bundle has no Beamer entry point
    (tmp_path / "notes.tex").write_text("Notes", encoding="utf-8")

    with pytest.raises(MainFileNotFoundError, match="No Beamer main file"):
        find_main_file(tmp_path)


def test_find_main_file_lists_multiple_candidates(tmp_path: Path) -> None:
    # Report every candidate when selection is ambiguous
    (tmp_path / "first.tex").write_text(BEAMER_SOURCE, encoding="utf-8")
    (tmp_path / "second.tex").write_text(BEAMER_SOURCE, encoding="utf-8")

    with pytest.raises(MultipleMainFilesError) as error:
        find_main_file(tmp_path)

    assert "first.tex" in str(error.value)
    assert "second.tex" in str(error.value)


def test_find_main_file_accepts_valid_override(tmp_path: Path) -> None:
    # Select one candidate when the caller names it
    (tmp_path / "first.tex").write_text(BEAMER_SOURCE, encoding="utf-8")
    (tmp_path / "second.tex").write_text(BEAMER_SOURCE, encoding="utf-8")

    assert find_main_file(tmp_path, "second.tex") == "second.tex"


def test_bundle_from_folder_filters_generated_files(tmp_path: Path) -> None:
    # Normalize a folder bundle and remove build junk
    (tmp_path / "main.tex").write_text(BEAMER_SOURCE, encoding="utf-8")
    (tmp_path / "chapter.tex").write_text("Chapter", encoding="utf-8")
    (tmp_path / "main.pdf").write_bytes(b"build")
    (tmp_path / "other.pdf").write_bytes(b"source")
    (tmp_path / "main.log").write_text("build", encoding="utf-8")
    (tmp_path / ".DS_Store").write_bytes(b"metadata")

    bundle = Bundle.from_path(tmp_path)

    assert bundle.root == tmp_path.resolve()
    assert bundle.main_file == "main.tex"
    assert bundle.files == ["chapter.tex", "main.tex", "other.pdf"]


def test_bundle_from_zip_extracts_nested_project(tmp_path: Path) -> None:
    # Normalize an archive bundle with a top level folder
    archive_path = tmp_path / "slides.zip"
    _write_zip(
        archive_path,
        {
            "course/main.tex": BEAMER_SOURCE,
            "course/figs/chart.png": "image",
            "course/main.aux": "build",
        },
    )

    bundle = Bundle.from_path(archive_path)
    try:
        assert bundle.main_file == "course/main.tex"
        assert bundle.files == ["course/figs/chart.png", "course/main.tex"]
        assert (bundle.root / "course/main.tex").is_file()
    finally:
        shutil.rmtree(bundle.root)


def test_bundle_rejects_non_zip_file(tmp_path: Path) -> None:
    # Reject unsupported bundle input paths
    source = tmp_path / "main.tex"
    source.write_text(BEAMER_SOURCE, encoding="utf-8")

    with pytest.raises(BundlePathError, match="folder or zip"):
        Bundle.from_path(source)

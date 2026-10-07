import stat
import zipfile
from pathlib import Path

import pytest

from a11y_pipeline.bundle.unzip import (
    ArchiveLimitError,
    UnsafeArchiveError,
    safe_extract_zip,
)


def _write_zip(path: Path, files: dict[str, bytes]) -> None:
    # Create a small archive from test data
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)


def test_safe_extract_zip_extracts_source_files(tmp_path: Path) -> None:
    # Extract regular nested source files
    archive_path = tmp_path / "project.zip"
    _write_zip(
        archive_path,
        {
            "main.tex": b"source",
            "figs/image.png": b"image",
        },
    )

    output = tmp_path / "output"
    files = safe_extract_zip(archive_path, output)

    assert files == ["figs/image.png", "main.tex"]
    assert (output / "main.tex").read_bytes() == b"source"
    assert (output / "figs/image.png").read_bytes() == b"image"


@pytest.mark.parametrize(
    "member_name",
    (
        "../escape.tex",
        "folder/../../escape.tex",
        "/absolute.tex",
        "C:/absolute.tex",
        "\\\\server\\share\\absolute.tex",
    ),
)
def test_safe_extract_zip_rejects_unsafe_paths(
    tmp_path: Path,
    member_name: str,
) -> None:
    # Reject archive paths that can escape the destination
    archive_path = tmp_path / "unsafe.zip"
    _write_zip(archive_path, {member_name: b"unsafe"})

    with pytest.raises(UnsafeArchiveError):
        safe_extract_zip(archive_path, tmp_path / "output")

    assert not (tmp_path / "escape.tex").exists()


def test_safe_extract_zip_rejects_symlinks(tmp_path: Path) -> None:
    # Reject symbolic links even when their targets look local
    archive_path = tmp_path / "symlink.zip"
    link = zipfile.ZipInfo("linked.tex")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(link, "main.tex")

    with pytest.raises(UnsafeArchiveError, match="symbolic link"):
        safe_extract_zip(archive_path, tmp_path / "output")


def test_safe_extract_zip_enforces_file_count_limit(tmp_path: Path) -> None:
    # Reject archives with too many files
    archive_path = tmp_path / "many.zip"
    _write_zip(
        archive_path,
        {
            "one.tex": b"one",
            "two.tex": b"two",
        },
    )

    with pytest.raises(ArchiveLimitError, match="2 files"):
        safe_extract_zip(archive_path, tmp_path / "output", max_files=1)


def test_safe_extract_zip_enforces_size_limit(tmp_path: Path) -> None:
    # Reject archives whose expanded content is too large
    archive_path = tmp_path / "large.zip"
    _write_zip(archive_path, {"main.tex": b"12345"})

    with pytest.raises(ArchiveLimitError, match="5 bytes"):
        safe_extract_zip(archive_path, tmp_path / "output", max_uncompressed_size=4)


def test_safe_extract_zip_filters_junk_and_matching_pdf(tmp_path: Path) -> None:
    # Ignore platform metadata and generated TeX files
    archive_path = tmp_path / "junk.zip"
    _write_zip(
        archive_path,
        {
            "__MACOSX/._main.tex": b"metadata",
            ".DS_Store": b"metadata",
            "main.tex": b"source",
            "main.pdf": b"build",
            "main.aux": b"build",
            "main.synctex.gz": b"build",
            "references.pdf": b"source",
        },
    )

    output = tmp_path / "output"
    files = safe_extract_zip(archive_path, output)

    assert files == ["main.tex", "references.pdf"]
    assert not (output / "main.pdf").exists()
    assert not (output / "main.aux").exists()

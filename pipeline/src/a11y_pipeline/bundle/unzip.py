import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath

DEFAULT_MAX_UNCOMPRESSED_SIZE = 200 * 1024 * 1024
DEFAULT_MAX_FILES = 5_000
BUILD_SUFFIXES = {
    ".aux",
    ".log",
    ".nav",
    ".out",
    ".snm",
    ".toc",
}


class UnsafeArchiveError(ValueError):
    pass


class ArchiveLimitError(ValueError):
    pass


def is_junk_path(path: str | Path, tex_files: set[str] | None = None) -> bool:
    # Identify files that do not belong in a source bundle
    normalized = str(path).replace("\\", "/")
    candidate = PurePosixPath(normalized)
    if "__MACOSX" in candidate.parts or candidate.name == ".DS_Store":
        return True
    lower_name = candidate.name.lower()
    if lower_name.endswith(".synctex.gz"):
        return True
    if candidate.suffix.lower() in BUILD_SUFFIXES:
        return True
    if candidate.suffix.lower() != ".pdf" or tex_files is None:
        return False
    pdf_stem = candidate.with_suffix("").as_posix()
    return f"{pdf_stem}.tex" in tex_files


def _safe_member_path(name: str) -> PurePosixPath:
    # Validate an archive member before creating files
    if "\x00" in name:
        raise UnsafeArchiveError("Archive member contains a null byte")
    normalized = name.replace("\\", "/")
    windows_path = PureWindowsPath(normalized)
    member_path = PurePosixPath(normalized)
    if member_path.is_absolute() or windows_path.is_absolute() or windows_path.drive:
        raise UnsafeArchiveError(f"Archive member uses an absolute path: {name}")
    if ".." in member_path.parts:
        raise UnsafeArchiveError(f"Archive member escapes the destination: {name}")
    return member_path


def _is_symlink(member: zipfile.ZipInfo) -> bool:
    # Detect links stored with Unix mode metadata
    mode = member.external_attr >> 16
    return stat.S_ISLNK(mode)


def _tex_members(members: list[zipfile.ZipInfo]) -> set[str]:
    # Collect source names used to filter matching build PDFs
    tex_files: set[str] = set()
    for member in members:
        path = _safe_member_path(member.filename)
        if path.suffix.lower() == ".tex":
            tex_files.add(path.as_posix())
    return tex_files


def safe_extract_zip(
    archive_path: Path,
    destination: Path,
    *,
    max_uncompressed_size: int = DEFAULT_MAX_UNCOMPRESSED_SIZE,
    max_files: int = DEFAULT_MAX_FILES,
) -> list[str]:
    # Extract a zip while enforcing bundle safety limits
    destination.mkdir(parents=True, exist_ok=True)
    destination_resolved = destination.resolve()
    extracted: list[str] = []
    with zipfile.ZipFile(archive_path) as archive:
        members = archive.infolist()
        file_count = 0
        total_size = 0
        for member in members:
            _safe_member_path(member.filename)
            if _is_symlink(member):
                raise UnsafeArchiveError(f"Archive member is a symbolic link: {member.filename}")
            if not member.is_dir():
                file_count += 1
                total_size += member.file_size
        if file_count > max_files:
            raise ArchiveLimitError(
                f"Archive contains {file_count} files and the limit is {max_files}"
            )
        if total_size > max_uncompressed_size:
            raise ArchiveLimitError(
                f"Archive expands to {total_size} bytes and the limit is {max_uncompressed_size}"
            )

        tex_files = _tex_members(members)
        for member in members:
            member_path = _safe_member_path(member.filename)
            if member.is_dir() or is_junk_path(member_path, tex_files):
                continue
            output_path = destination.joinpath(*member_path.parts)
            output_resolved = output_path.resolve()
            if not output_resolved.is_relative_to(destination_resolved):
                raise UnsafeArchiveError(
                    f"Archive member escapes the destination: {member.filename}"
                )
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, output_path.open("wb") as target:
                shutil.copyfileobj(source, target)
            extracted.append(member_path.as_posix())
    extracted.sort()
    return extracted

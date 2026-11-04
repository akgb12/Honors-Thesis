import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from a11y_pipeline.bundle.mainfile import find_main_file
from a11y_pipeline.bundle.unzip import (
    DEFAULT_MAX_FILES,
    DEFAULT_MAX_UNCOMPRESSED_SIZE,
    is_junk_path,
    safe_extract_zip,
)


class BundlePathError(ValueError):
    pass


@dataclass(frozen=True)
class Bundle:
    root: Path
    main_file: str
    files: list[str]

    @classmethod
    def from_path(
        cls,
        path: Path | str,
        main_file: str | None = None,
        *,
        max_uncompressed_size: int = DEFAULT_MAX_UNCOMPRESSED_SIZE,
        max_files: int = DEFAULT_MAX_FILES,
    ) -> "Bundle":
        # Load a source folder or zip as a normalized bundle
        source = Path(path).expanduser()
        temporary_root: Path | None = None
        if source.is_dir():
            root = source.resolve()
        elif source.is_file() and source.suffix.lower() == ".zip":
            if not zipfile.is_zipfile(source):
                raise BundlePathError(f"File is not a valid zip archive: {source}")
            temporary_root = Path(tempfile.mkdtemp(prefix="a11y-bundle-"))
            try:
                safe_extract_zip(
                    source,
                    temporary_root,
                    max_uncompressed_size=max_uncompressed_size,
                    max_files=max_files,
                )
            except Exception:
                shutil.rmtree(temporary_root, ignore_errors=True)
                raise
            root = temporary_root
        else:
            raise BundlePathError(f"Bundle path must be a folder or zip file: {source}")

        try:
            detected_main = find_main_file(root, main_file)
            files = _bundle_files(root)
        except Exception:
            if temporary_root is not None:
                shutil.rmtree(temporary_root, ignore_errors=True)
            raise
        return cls(root=root, main_file=detected_main, files=files)


def _bundle_files(root: Path) -> list[str]:
    # List normalized source files without generated junk
    tex_files: set[str] = set()
    all_files: list[tuple[Path, str]] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        all_files.append((path, relative))
        if path.suffix.lower() == ".tex":
            tex_files.add(relative)

    files: list[str] = []
    for _, relative in all_files:
        if not is_junk_path(relative, tex_files):
            files.append(relative)
    files.sort()
    return files

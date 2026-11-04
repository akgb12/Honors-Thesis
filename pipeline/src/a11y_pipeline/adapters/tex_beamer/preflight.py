import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pylatexenc.latexwalker import (
    LatexCommentNode,
    LatexEnvironmentNode,
    LatexGroupNode,
    LatexMacroNode,
    LatexWalker,
    get_default_latex_context_db,
)
from pylatexenc.macrospec import MacroSpec

from a11y_pipeline.bundle.bundle import Bundle

IMAGE_EXTENSIONS = (".pdf", ".png", ".jpg", ".jpeg", ".eps")
ENGINE_PACKAGES = {"fontspec", "unicode-math"}
THEME_PREFIXES = {
    "usetheme": "beamertheme",
    "usecolortheme": "beamercolortheme",
    "usefonttheme": "beamerfonttheme",
    "useinnertheme": "beamerinnertheme",
    "useoutertheme": "beameroutertheme",
}


@dataclass(frozen=True)
class PreflightIssue:
    code: str
    severity: Literal["warning", "critical"]
    message: str
    source_file: str
    line: int
    dependency: str | None = None


@dataclass(frozen=True)
class PreflightResult:
    ok: bool
    missing_images: list[str]
    missing_critical: list[str]
    assets: list[str]
    issues: list[PreflightIssue]


def _latex_context():
    # Register dependency macros so their arguments become parsed nodes
    context = get_default_latex_context_db()
    macros = [
        MacroSpec("addplot", "["),
        MacroSpec("bibliography", "{"),
        MacroSpec("documentclass", "[{"),
        MacroSpec("graphicspath", "{"),
        MacroSpec("include", "{"),
        MacroSpec("includegraphics", "[{"),
        MacroSpec("input", "{"),
        MacroSpec("usepackage", "[{"),
        MacroSpec("usetheme", "[{"),
        MacroSpec("usecolortheme", "[{"),
        MacroSpec("usefonttheme", "[{"),
        MacroSpec("useinnertheme", "[{"),
        MacroSpec("useoutertheme", "[{"),
    ]
    context.add_context_category("a11y-preflight", macros=macros, prepend=True)
    return context


def _group_text(node: LatexGroupNode | None) -> str:
    # Return the source text inside one argument group
    if node is None:
        return ""
    text = node.latex_verbatim()
    if len(text) >= 2 and text[0] == "{" and text[-1] == "}":
        return text[1:-1].strip()
    return text.strip()


def _required_argument(node: LatexMacroNode) -> LatexGroupNode | None:
    # Return the last required group parsed for a macro
    if node.nodeargd is None:
        return None
    for argument in reversed(node.nodeargd.argnlist):
        if isinstance(argument, LatexGroupNode):
            return argument
    return None


def _split_names(value: str) -> list[str]:
    # Split a comma separated dependency argument
    names: list[str] = []
    for item in value.split(","):
        name = item.strip()
        if name:
            names.append(name)
    return names


_END_DOCUMENT = re.compile(r"^[^%\n]*?\\end\{document\}", re.MULTILINE)


def _text_before_end_document(text: str) -> str:
    # LaTeX ignores everything after an uncommented end of document
    match = _END_DOCUMENT.search(text)
    return text if match is None else text[: match.end()]


class _Scanner:
    def __init__(self, bundle: Bundle):
        # Track state while walking source dependencies
        self.bundle = bundle
        self.root = bundle.root.resolve()
        self.assets: set[str] = set()
        self.missing_images: set[str] = set()
        self.missing_critical: set[str] = set()
        self.issues: list[PreflightIssue] = []
        self.graphic_paths: list[str] = []
        self.scanned_sources: set[str] = set()
        self.kpsewhich = shutil.which("kpsewhich")
        self.kpse_cache: dict[str, bool] = {}

    def run(self) -> PreflightResult:
        # Scan the main file and every reachable local source
        self._scan_source(self.bundle.main_file)
        critical = False
        for issue in self.issues:
            if issue.severity == "critical":
                critical = True
                break
        return PreflightResult(
            ok=not critical,
            missing_images=sorted(self.missing_images),
            missing_critical=sorted(self.missing_critical),
            assets=sorted(self.assets),
            issues=self.issues,
        )

    def _scan_source(self, relative_path: str) -> None:
        # Parse one source file once and walk its nodes
        if relative_path in self.scanned_sources:
            return
        self.scanned_sources.add(relative_path)
        source_path = self.root / relative_path
        try:
            text = source_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            self._critical(
                "source_unreadable",
                relative_path,
                1,
                relative_path,
                f"Cannot read source file {relative_path}: {error}",
            )
            return
        text = _text_before_end_document(text)
        walker = LatexWalker(text, latex_context=_latex_context(), tolerant_parsing=True)
        nodes, _, _ = walker.get_latex_nodes()
        self._scan_nodes(nodes, relative_path, text)

    def _scan_nodes(self, nodes: list, source_file: str, text: str) -> None:
        # Visit dependency macros in parsed source order
        for index, node in enumerate(nodes):
            if isinstance(node, LatexMacroNode):
                self._scan_macro(node, nodes, index, source_file, text)
                if node.nodeargd is not None:
                    for argument in node.nodeargd.argnlist:
                        if isinstance(argument, LatexGroupNode):
                            self._scan_nodes(argument.nodelist, source_file, text)
            elif isinstance(node, LatexEnvironmentNode) or isinstance(node, LatexGroupNode):
                self._scan_nodes(node.nodelist, source_file, text)

    def _scan_macro(
        self,
        node: LatexMacroNode,
        siblings: list,
        index: int,
        source_file: str,
        text: str,
    ) -> None:
        # Dispatch one parsed macro to its dependency handler
        line = text.count("\n", 0, node.pos) + 1
        name = node.macroname
        argument = _group_text(_required_argument(node))
        if name == "graphicspath":
            self._set_graphic_paths(_required_argument(node))
        elif name == "includegraphics" and argument:
            self._image(argument, source_file, line)
        elif name == "input" or name == "include":
            if argument:
                self._source_dependency(argument, source_file, line, name)
        elif name == "usepackage":
            self._packages(argument, source_file, line)
        elif name in THEME_PREFIXES:
            self._themes(name, argument, source_file, line)
        elif name == "bibliography":
            self._bibliography(argument, source_file, line)
        elif name == "documentclass":
            self._document_class(argument, source_file, line)
        elif name == "addplot":
            table_path = self._addplot_table_path(siblings, index)
            if table_path:
                self._data_file(table_path, source_file, line)

    def _set_graphic_paths(self, argument: LatexGroupNode | None) -> None:
        # Replace active graphic search folders from parsed groups
        if argument is None:
            return
        paths: list[str] = []
        for node in argument.nodelist:
            if isinstance(node, LatexGroupNode):
                path = _group_text(node)
                if path:
                    paths.append(path)
        self.graphic_paths = paths

    def _image(self, reference: str, source_file: str, line: int) -> None:
        # Resolve one image with graphic paths and extension fallbacks
        search_folders = [""]
        for folder in self.graphic_paths:
            search_folders.append(folder)
        resolved = self._resolve(reference, IMAGE_EXTENSIONS, search_folders)
        if resolved is not None:
            self.assets.add(resolved)
            return
        self.missing_images.add(reference)
        self._issue(
            "missing_image",
            "warning",
            source_file,
            line,
            reference,
            f"Image dependency was not found: {reference}",
        )

    def _source_dependency(
        self,
        reference: str,
        source_file: str,
        line: int,
        macro_name: str,
    ) -> None:
        # Resolve and recursively scan an included TeX source
        resolved = self._resolve(reference, (".tex",), [""])
        if resolved is None:
            self._critical(
                f"missing_{macro_name}",
                source_file,
                line,
                reference,
                f"Required source dependency was not found: {reference}",
            )
            return
        self.assets.add(resolved)
        self._scan_source(resolved)

    def _packages(self, argument: str, source_file: str, line: int) -> None:
        # Check local or installed packages and engine restrictions
        for package in _split_names(argument):
            if package in ENGINE_PACKAGES:
                self._issue(
                    "engine_unsupported",
                    "critical",
                    source_file,
                    line,
                    package,
                    f"Package {package} requires an unsupported TeX engine",
                )
            filename = package
            if not filename.lower().endswith(".sty"):
                filename = f"{filename}.sty"
            resolved = self._resolve(filename, (), [""])
            if resolved is not None:
                self.assets.add(resolved)
                self._scan_source(resolved)
            elif not self._installed(filename):
                self._critical(
                    "missing_package",
                    source_file,
                    line,
                    filename,
                    f"Package dependency was not found: {filename}",
                )

    def _themes(
        self,
        macro_name: str,
        argument: str,
        source_file: str,
        line: int,
    ) -> None:
        # Check local or installed Beamer theme files
        prefix = THEME_PREFIXES[macro_name]
        for theme in _split_names(argument):
            filename = f"{prefix}{theme}.sty"
            resolved = self._resolve(filename, (), [""])
            if resolved is not None:
                self.assets.add(resolved)
                self._scan_source(resolved)
            elif not self._installed(filename):
                self._critical(
                    "missing_theme",
                    source_file,
                    line,
                    filename,
                    f"Beamer theme dependency was not found: {filename}",
                )

    def _bibliography(self, argument: str, source_file: str, line: int) -> None:
        # Resolve every bibliography database in one command
        for reference in _split_names(argument):
            resolved = self._resolve(reference, (".bib",), [""])
            if resolved is None:
                self._critical(
                    "missing_bibliography",
                    source_file,
                    line,
                    reference,
                    f"Bibliography dependency was not found: {reference}",
                )
            else:
                self.assets.add(resolved)

    def _document_class(self, argument: str, source_file: str, line: int) -> None:
        # Check a local or installed document class
        if not argument:
            return
        filename = argument
        if not filename.lower().endswith(".cls"):
            filename = f"{filename}.cls"
        resolved = self._resolve(filename, (), [""])
        if resolved is not None:
            self.assets.add(resolved)
            self._scan_source(resolved)
        elif not self._installed(filename):
            self._critical(
                "missing_class",
                source_file,
                line,
                filename,
                f"Document class dependency was not found: {filename}",
            )

    def _data_file(self, reference: str, source_file: str, line: int) -> None:
        # Resolve a data file used by a plot table
        resolved = self._resolve(reference, (), [""])
        if resolved is None:
            self._critical(
                "missing_plot_data",
                source_file,
                line,
                reference,
                f"Plot data dependency was not found: {reference}",
            )
        else:
            self.assets.add(resolved)

    def _addplot_table_path(self, siblings: list, index: int) -> str | None:
        # Read the group following an addplot table clause
        saw_table = False
        position = index + 1
        while position < len(siblings):
            sibling = siblings[position]
            if isinstance(sibling, LatexCommentNode):
                position += 1
                continue
            if isinstance(sibling, LatexGroupNode):
                if saw_table:
                    return _group_text(sibling)
                return None
            chars = getattr(sibling, "chars", None)
            if chars is None:
                return None
            stripped = chars.lstrip()
            if not saw_table:
                if not stripped.startswith("table"):
                    return None
                remainder = stripped[len("table") :]
                if remainder and not remainder[0].isspace() and remainder[0] != "[":
                    return None
                saw_table = True
            position += 1
        return None

    def _resolve(
        self,
        reference: str,
        extensions: tuple[str, ...],
        search_folders: list[str],
    ) -> str | None:
        # Resolve a dependency without allowing bundle escapes
        if "\\" in reference:
            return None
        reference_path = Path(reference)
        if reference_path.is_absolute():
            return None
        names: list[Path] = [reference_path]
        if not reference_path.suffix:
            for extension in extensions:
                names.append(Path(f"{reference}{extension}"))
        for folder in search_folders:
            folder_path = Path(folder)
            for name in names:
                candidate = (self.root / folder_path / name).resolve()
                if not candidate.is_relative_to(self.root):
                    continue
                if candidate.is_file():
                    return candidate.relative_to(self.root).as_posix()
        return None

    def _installed(self, filename: str) -> bool:
        # Ask TeX for external files only when its lookup tool exists
        if self.kpsewhich is None:
            return True
        if filename in self.kpse_cache:
            return self.kpse_cache[filename]
        try:
            completed = subprocess.run(
                [self.kpsewhich, filename],
                capture_output=True,
                check=False,
                text=True,
                timeout=10,
            )
            found = completed.returncode == 0 and bool(completed.stdout.strip())
        except (OSError, subprocess.SubprocessError):
            found = True
        self.kpse_cache[filename] = found
        return found

    def _critical(
        self,
        code: str,
        source_file: str,
        line: int,
        dependency: str,
        message: str,
    ) -> None:
        # Record a missing dependency that blocks compilation
        self.missing_critical.add(dependency)
        self._issue(code, "critical", source_file, line, dependency, message)

    def _issue(
        self,
        code: str,
        severity: Literal["warning", "critical"],
        source_file: str,
        line: int,
        dependency: str | None,
        message: str,
    ) -> None:
        # Add a structured preflight issue
        self.issues.append(
            PreflightIssue(
                code=code,
                severity=severity,
                message=message,
                source_file=source_file,
                line=line,
                dependency=dependency,
            )
        )


def preflight(bundle: Bundle) -> PreflightResult:
    # Scan a normalized bundle before parsing or model work
    return _Scanner(bundle).run()

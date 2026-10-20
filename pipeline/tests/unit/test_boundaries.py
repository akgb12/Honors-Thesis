import ast
from pathlib import Path

SOURCE_ROOT = Path(__file__).parents[2] / "src"
PACKAGE_ROOT = SOURCE_ROOT / "a11y_pipeline"
TEX_ADAPTER_ROOT = PACKAGE_ROOT / "adapters" / "tex_beamer"
ADAPTER_REGISTRY = PACKAGE_ROOT / "adapters" / "__init__.py"


def _python_files() -> list[Path]:
    # Collect pipeline modules in stable order
    files: list[Path] = []
    for path in PACKAGE_ROOT.rglob("*.py"):
        files.append(path)
    files.sort()
    return files


def _imports(path: Path) -> list[str]:
    # Read absolute import names from one module
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.append(node.module)
    return names


def test_tex_beamer_imports_stay_inside_adapter_boundary() -> None:
    # Keep format specific imports inside the adapter
    violations: list[str] = []
    for path in _python_files():
        if path.is_relative_to(TEX_ADAPTER_ROOT) or path == ADAPTER_REGISTRY:
            continue
        for name in _imports(path):
            if name == "a11y_pipeline.adapters.tex_beamer":
                violations.append(f"{path.relative_to(SOURCE_ROOT)} imports {name}")
            elif name.startswith("a11y_pipeline.adapters.tex_beamer."):
                violations.append(f"{path.relative_to(SOURCE_ROOT)} imports {name}")
    assert violations == []


def test_pipeline_never_imports_django() -> None:
    # Keep the pipeline independent from the web backend
    violations: list[str] = []
    for path in _python_files():
        for name in _imports(path):
            if name == "django" or name.startswith("django."):
                violations.append(f"{path.relative_to(SOURCE_ROOT)} imports {name}")
    assert violations == []

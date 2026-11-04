import subprocess
from pathlib import Path
from typing import Any

import pikepdf
import pytest

from a11y_pipeline.adapters.tex_beamer.aux_reader import apply_aux_mapping, read_aux
from a11y_pipeline.adapters.tex_beamer.builder import build
from a11y_pipeline.adapters.tex_beamer.compile import compile_project
from a11y_pipeline.adapters.tex_beamer.markers import inject_markers
from a11y_pipeline.adapters.tex_beamer.parser import parse_file
from a11y_pipeline.adapters.tex_beamer.preflight import preflight
from a11y_pipeline.adapters.tex_beamer.working_copy import create_working_copies
from a11y_pipeline.adapters.tex_beamer.writer import (
    verify_updated_project,
    write_updated_project,
)
from a11y_pipeline.bundle.bundle import Bundle
from a11y_pipeline.evaluation.pdf_checks import check_pdf, read_parent_tree, scan_page_content
from a11y_pipeline.render.pixeldiff import compare_pdf_pixels
from a11y_pipeline.synthesis.tagger import tag_pdf

FIXTURES = Path(__file__).parents[1] / "fixtures"


@pytest.mark.tex
def test_m10_tagged_pdf_and_updated_source_acceptance(tmp_path: Path) -> None:
    # Verify deterministic PDF tagging and safe source output
    fixture = FIXTURES / "lecture_sample"
    bundle = Bundle.from_path(fixture)
    ir = build(parse_file(fixture), preflight(bundle))
    copies = create_working_copies(bundle, ir, tmp_path / "work")
    inject_markers(ir, copies.marked)
    original = compile_project(copies.original, bundle.main_file)
    marked = compile_project(copies.marked, bundle.main_file)
    mapped = apply_aux_mapping(ir, read_aux(marked.aux_path))
    _set_figure_descriptions(mapped)

    tagged_path = tmp_path / "output" / "tagged.pdf"
    tagging = tag_pdf(marked.pdf_path, mapped, tagged_path)
    checks = check_pdf(tagged_path, mapped)
    pixel_check = compare_pdf_pixels(original.pdf_path, tagged_path)

    assert tagging.issues == []
    assert checks.passed
    assert checks.passed_check_count == len(checks.checks)
    assert pixel_check.identical
    assert pixel_check.different_pages == []
    _assert_parent_tree_and_artifacts(tagged_path, mapped)
    _assert_structure_order(tagged_path)
    _assert_drawing_operators_unchanged(marked.pdf_path, tagged_path)

    updated_root = tmp_path / "output" / "updated_project"
    diff_path = tmp_path / "output" / "changes.diff"
    writer = write_updated_project(bundle, mapped, updated_root, diff_path)
    verification = verify_updated_project(
        original.pdf_path,
        writer.project_root,
        bundle.main_file,
    )
    updated = (updated_root / bundle.main_file).read_text(encoding="utf-8")
    diff = diff_path.read_text(encoding="utf-8")

    assert writer.issues == []
    assert verification.compile_result.errors == 0
    assert verification.compile_result.page_count == original.page_count
    assert verification.pixel_check.identical
    assert r"\hypersetup{pdftitle={Introduction to Machine Learning}, pdflang={en-US}}" in updated
    assert r"alt={Scatter plot of observed points and a fitted regression line.}" in updated
    assert "% a11y-alt: Five folds appear in a row" in updated
    _assert_tikz_comments_wrapped(updated)
    _assert_diff_edit_kinds(diff)
    assert (fixture / "main.aux").exists() is False
    assert (fixture / "main.pdf").exists() is False


def _set_figure_descriptions(ir: Any) -> None:
    # Add deterministic fixture descriptions
    regression = ir.elements["slide_03/figure_01"]
    regression.accessibility.alt_text = (
        "Scatter plot of observed points and a fitted regression line."
    )
    regression.accessibility.status = "model_generated"
    diagram = ir.elements["slide_04/figure_01"]
    diagram.accessibility.alt_text = (
        "Five folds appear in a row with the third position selected as the test fold."
    )
    diagram.accessibility.extended_description = (
        "The remaining four folds are shown as training folds while the selected position "
        "is highlighted in blue."
    )
    diagram.accessibility.status = "model_generated"


def _assert_parent_tree_and_artifacts(path: Path, ir: Any) -> None:
    # Check final MCID ownership and earlier overlay artifacts
    figure = ir.elements["slide_04/figure_01"]
    with pikepdf.open(path) as pdf:
        tree = read_parent_tree(pdf.Root.StructTreeRoot.ParentTree)
        final_page = figure.render.pages[-1]
        key = int(pdf.pages[final_page - 1].obj.StructParents)
        assert tree[key][figure.mcid] is not None
        earlier = figure.render.pages[0]
        scan = scan_page_content(pdf.pages[earlier - 1], earlier)
        assert figure.mcid not in scan.mcid_counts
        found_artifact = False
        for operands, operator in pikepdf.parse_content_stream(pdf.pages[earlier - 1]):
            if str(operator) == "BMC" and operands and str(operands[0]) == "/Artifact":
                found_artifact = True
        assert found_artifact


def _assert_structure_order(path: Path) -> None:
    # Check structure roles and pdfinfo text order
    expected = [
        (
            "Sect",
            [
                ("Sect", ["H1", "P", "P", "P", "P"]),
            ],
        ),
        (
            "Sect",
            [
                "H2",
                (
                    "L",
                    [
                        ("LI", ["LBody"]),
                        ("LI", ["LBody"]),
                        (
                            "LI",
                            [
                                "LBody",
                                (
                                    "L",
                                    [
                                        ("LI", ["LBody"]),
                                        ("LI", ["LBody"]),
                                    ],
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        ),
        ("Sect", ["H2", "P", "Formula", "Figure"]),
        (
            "Sect",
            [
                "H2",
                (
                    "L",
                    [
                        ("LI", ["LBody"]),
                        ("LI", ["LBody"]),
                    ],
                ),
                "Figure",
                "P",
            ],
        ),
        ("Sect", ["H2", "P", "P"]),
        ("Sect", ["H2"]),
    ]
    with pikepdf.open(path) as pdf:
        document = pdf.Root.StructTreeRoot.K
        assert str(document.S) == "/Document"
        actual = _role_children(document.K)
    assert actual == expected
    completed = subprocess.run(
        ["pdfinfo", "-struct-text", str(path)],
        capture_output=True,
        check=True,
        text=True,
    )
    structure_text = completed.stdout
    assert "Document\n  Sect\n    Sect\n      H1 (block)" in structure_text
    assert (
        '  Sect\n    H2 (block)\n      "CourseLogistics"\n'
        "    L (block)\n      LI (block)\n        LBody (block)"
    ) in structure_text
    assert (
        '  Sect\n    H2 (block)\n      "LinearModels"\n    P (block)\n      "Amodelpredicts'
    ) in structure_text
    formula_position = structure_text.find("    Formula [")
    figure_position = structure_text.find("    Figure [")
    assert formula_position > 0
    assert figure_position > formula_position


def _role_children(value: Any) -> list[Any]:
    # Convert structure objects to comparable nested roles
    children: list[Any] = []
    for child in value:
        role = str(child.S).removeprefix("/")
        nested = child.K
        if isinstance(nested, pikepdf.Array):
            children.append((role, _role_children(nested)))
        else:
            children.append(role)
    return children


def _assert_drawing_operators_unchanged(marked: Path, tagged: Path) -> None:
    # Compare every non marker content operation
    with pikepdf.open(marked) as original:
        with pikepdf.open(tagged) as candidate:
            assert len(original.pages) == len(candidate.pages)
            for index in range(len(original.pages)):
                first = _drawing_operations(original.pages[index])
                second = _drawing_operations(candidate.pages[index])
                assert first == second


def _drawing_operations(page: Any) -> list[bytes]:
    # Serialize content operations except marked content boundaries
    operations: list[bytes] = []
    for operands, operator in pikepdf.parse_content_stream(page):
        if str(operator) in {"BDC", "BMC", "EMC"}:
            continue
        operations.append(pikepdf.unparse_content_stream([(operands, operator)]))
    return operations


def _assert_tikz_comments_wrapped(text: str) -> None:
    # Check every generated TikZ comment line width
    lines = text.splitlines()
    count = 0
    for line in lines:
        stripped = line.lstrip()
        if not stripped.startswith("% a11y-alt:"):
            continue
        count += 1
        assert len(line) <= 100
    assert count >= 2


def _assert_diff_edit_kinds(diff: str) -> None:
    # Restrict the unified diff to three approved edit kinds
    kinds: set[str] = set()
    for line in diff.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            added = line[1:].lstrip()
            if added.startswith(r"\hypersetup"):
                kinds.add("metadata")
            elif r"\includegraphics" in added and "alt={" in added:
                kinds.add("image_alt")
            elif added.startswith("% a11y-alt:"):
                kinds.add("tikz_alt")
            else:
                pytest.fail(f"Unexpected added diff line: {line}")
        elif line.startswith("-"):
            removed = line[1:]
            assert r"\includegraphics" in removed
    assert kinds == {"metadata", "image_alt", "tikz_alt"}

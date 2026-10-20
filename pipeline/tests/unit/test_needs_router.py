import shutil
from pathlib import Path

import pytest

from a11y_pipeline.adapters.tex_beamer.builder import build
from a11y_pipeline.adapters.tex_beamer.parser import parse_file
from a11y_pipeline.adapters.tex_beamer.preflight import preflight
from a11y_pipeline.analysis.needs import Task, analyze_needs
from a11y_pipeline.bundle.bundle import Bundle
from a11y_pipeline.routing.router import route, route_follow_ups

FIXTURES = Path(__file__).parents[1] / "fixtures"


def _lecture_document(path: Path):
    # Build the lecture document without model work
    bundle = Bundle.from_path(path)
    return build(parse_file(path), preflight(bundle))


def _task_ids(tasks: list[Task]) -> list[str]:
    # Collect task identifiers in routing order
    identifiers: list[str] = []
    for task in tasks:
        identifiers.append(task.element_id)
    return identifiers


def test_lecture_routes_only_two_figures() -> None:
    # Find only figures that need descriptions
    document = _lecture_document(FIXTURES / "lecture_sample")
    tasks = analyze_needs(document)
    assert _task_ids(tasks) == ["slide_03/figure_01", "slide_04/figure_01"]
    assert tasks[0].capability == "figure_description"


def test_missing_image_leaves_one_task(tmp_path: Path) -> None:
    # Skip model work for a missing image
    project = tmp_path / "lecture_sample"
    shutil.copytree(FIXTURES / "lecture_sample", project)
    shutil.rmtree(project / "figs")
    tasks = analyze_needs(_lecture_document(project))
    assert _task_ids(tasks) == ["slide_04/figure_01"]


def test_locked_figure_is_not_routed() -> None:
    # Protect locked human descriptions from model work
    document = _lecture_document(FIXTURES / "lecture_sample")
    document.elements["slide_03/figure_01"].accessibility.locked = True
    tasks = analyze_needs(document)
    assert _task_ids(tasks) == ["slide_04/figure_01"]


def test_router_supports_subsets_and_follow_ups() -> None:
    # Bind selected tasks and append chained work
    capability = object()
    registry = {"figure_description": capability}
    tasks = [
        Task(element_id="figure_01", capability="figure_description", reason="Initial"),
        Task(element_id="figure_02", capability="figure_description", reason="Initial"),
    ]
    routed = route(tasks, registry, {"figure_02"})
    assert len(routed) == 1
    assert routed[0].task.element_id == "figure_02"
    assert routed[0].capability is capability

    follow_up = Task(
        element_id="figure_03",
        capability="figure_description",
        reason="Follow up",
    )
    combined = route_follow_ups(routed, [follow_up], registry)
    assert len(combined) == 2
    assert combined[1].task == follow_up


def test_router_rejects_unknown_capability() -> None:
    # Fail clearly when a capability is unavailable
    task = Task(element_id="figure_01", capability="missing", reason="Unknown")
    with pytest.raises(KeyError, match="not registered"):
        route([task], {})

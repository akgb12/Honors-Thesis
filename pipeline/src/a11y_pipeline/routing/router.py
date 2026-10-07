from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from a11y_pipeline.analysis.needs import Task


@dataclass(frozen=True)
class RoutedTask:
    task: Task
    capability: Any


def route(
    tasks: list[Task],
    registry: Mapping[str, Any],
    element_ids: set[str] | None = None,
) -> list[RoutedTask]:
    # Bind selected tasks to registered capabilities
    routed: list[RoutedTask] = []
    for task in tasks:
        if element_ids is not None and task.element_id not in element_ids:
            continue
        capability = registry.get(task.capability)
        if capability is None:
            raise KeyError(f"capability is not registered: {task.capability}")
        routed.append(RoutedTask(task=task, capability=capability))
    return routed


def route_follow_ups(
    current: list[RoutedTask],
    follow_up_tasks: list[Task],
    registry: Mapping[str, Any],
    element_ids: set[str] | None = None,
) -> list[RoutedTask]:
    # Append routed follow up work without changing prior routes
    combined = list(current)
    combined.extend(route(follow_up_tasks, registry, element_ids))
    return combined

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from a11y_pipeline.adapters import get_adapter
from a11y_pipeline.bundle.bundle import Bundle
from a11y_pipeline.config import Settings
from a11y_pipeline.ir.serialize import dumps_document
from a11y_pipeline.models.anthropic_client import AnthropicModelClient
from a11y_pipeline.models.client import ModelClient, ModelRequest, ScriptValue
from a11y_pipeline.models.fake import FakeModelClient
from a11y_pipeline.runs.folder import CompletedRun, RunBlockedError, run_to_folder


def build_parser() -> argparse.ArgumentParser:
    # Build the three command accessibility interface
    parser = argparse.ArgumentParser(prog="a11y")
    commands = parser.add_subparsers(dest="command", required=True)

    preflight = commands.add_parser("preflight", help="Check project dependencies")
    preflight.add_argument("project", type=Path)
    preflight.add_argument("--main", dest="main_file")

    parse = commands.add_parser("parse", help="Parse a project into the canonical IR")
    parse.add_argument("project", type=Path)
    parse.add_argument("--main", dest="main_file")
    parse.add_argument("--json", action="store_true", dest="as_json")

    run = commands.add_parser("run", help="Run complete accessibility remediation")
    run.add_argument("project", type=Path)
    run.add_argument("--main", dest="main_file")
    run.add_argument(
        "--effort",
        choices=["baseline", "low", "medium", "high"],
        default="medium",
    )
    run.add_argument("--seed-weak", dest="seed_weak")
    run.add_argument("--out", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    # Dispatch one command without exposing configuration secrets
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "preflight":
            return _preflight_command(arguments)
        if arguments.command == "parse":
            return _parse_command(arguments)
        if arguments.command == "run":
            return _run_command(arguments)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    parser.error("Unknown command")
    return 2


def _preflight_command(arguments: argparse.Namespace) -> int:
    # Print dependency readiness before any model work
    bundle = Bundle.from_path(arguments.project, arguments.main_file)
    result = get_adapter("tex-beamer").preflight(bundle)
    print(f"main: {bundle.main_file}")
    print(f"status: {'ready' if result.ok else 'blocked'}")
    print(f"assets: {len(result.assets)}")
    for issue in result.issues:
        location = issue.source_file
        if issue.line:
            location += f":{issue.line}"
        print(f"{issue.severity}: {issue.code}: {location}: {issue.message}")
    if result.ok:
        return 0
    return 2


def _parse_command(arguments: argparse.Namespace) -> int:
    # Parse and print canonical JSON or the stable element summary
    bundle = Bundle.from_path(arguments.project, arguments.main_file)
    adapter = get_adapter("tex-beamer")
    preflight = adapter.preflight(bundle)
    document = adapter.build_ir(bundle, preflight)
    if arguments.as_json:
        print(dumps_document(document), end="")
    else:
        print(adapter.summarize(document), end="")
    return 0


def _run_command(arguments: argparse.Namespace) -> int:
    # Run remediation with the configured guarded model provider
    settings = Settings()
    client = _model_client(settings)
    output_root = arguments.out
    if output_root is None:
        output_root = settings.runs_dir
    try:
        completed = run_to_folder(
            arguments.project,
            client,
            settings,
            effort=arguments.effort,
            main_file=arguments.main_file,
            seed_weak_element_id=arguments.seed_weak,
            output_root=output_root,
        )
    except RunBlockedError as error:
        print(error.folder.root)
        print("Run blocked during preflight", file=sys.stderr)
        for issue in error.state.issues:
            print(f"{issue.severity}: {issue.code}: {issue.message}", file=sys.stderr)
        return 2
    _print_run_summary(completed)
    return 0


def _model_client(settings: Settings) -> ModelClient:
    # Construct only the provider selected by validated settings
    if settings.model_provider == "fake":
        return FakeModelClient(default_generator=_good_fake_response)
    return AnthropicModelClient(settings)


def _good_fake_response(request: ModelRequest) -> ScriptValue:
    # Return deterministic useful descriptions for local runs
    if request.element_id == "slide_04/figure_01":
        return {
            "alt_text": (
                "Five-fold cross-validation shows five folds in a row with the third "
                "position selected as the test fold."
            ),
            "extended_description": (
                "The remaining four folds are training folds while the selected test "
                "position is highlighted in blue."
            ),
            "decorative": False,
        }
    if request.element_id == "slide_03/figure_01":
        return {
            "alt_text": "Observed data points with a fitted regression line rising through them.",
            "extended_description": None,
            "decorative": False,
        }
    return {
        "alt_text": "A diagram presents the visible concepts and labels on the slide.",
        "extended_description": None,
        "decorative": False,
    }


def _print_run_summary(completed: CompletedRun) -> None:
    # Print the run path and compact one screen summary
    accessibility = _score_text(completed.stats.accessibility.value)
    fidelity = _score_text(completed.stats.fidelity.value)
    print(completed.folder.root)
    print(f"Preliminary A: {accessibility}")
    print(f"Preliminary F: {fidelity}")
    print(f"Stop reason: {completed.stats.stop_reason}")
    print(
        "Model usage: "
        f"{completed.stats.model_calls} calls, "
        f"{completed.stats.input_tokens} input tokens, "
        f"{completed.stats.output_tokens} output tokens, "
        f"${completed.stats.cost_usd:.6f}"
    )
    status_parts: list[str] = []
    for status in sorted(completed.stats.status_counts):
        count = completed.stats.status_counts[status]
        status_parts.append(f"{status}={count}")
    print("Statuses: " + ", ".join(status_parts))
    print(f"Report: {completed.folder.report_path}")


def _score_text(value: float | None) -> str:
    # Format one report score
    if value is None:
        return "N/A"
    return f"{value:.1f}"

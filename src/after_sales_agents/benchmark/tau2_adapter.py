"""Read and validate the official τ-bench Retail dataset without modifying it."""

from __future__ import annotations

import json
import os
import tomllib
from collections import Counter
from pathlib import Path
from typing import Any

from after_sales_agents.benchmark.models import (
    OfficialTaskSummary,
    RetailIntent,
    SubsetValidationReport,
    TaskSubsetManifest,
)

WRITE_TOOL_BY_INTENT = {
    RetailIntent.CANCEL: "cancel_pending_order",
    RetailIntent.RETURN: "return_delivered_order_items",
    RetailIntent.EXCHANGE: "exchange_delivered_order_items",
}

RETAIL_WRITE_TOOLS = frozenset(
    {
        "cancel_pending_order",
        "exchange_delivered_order_items",
        "modify_pending_order_address",
        "modify_pending_order_items",
        "modify_pending_order_payment",
        "modify_user_address",
        "return_delivered_order_items",
    }
)

REQUIRED_TAU2_PATHS = (
    Path("pyproject.toml"),
    Path("data/tau2/domains/retail/tasks.json"),
    Path("data/tau2/domains/retail/split_tasks.json"),
    Path("data/tau2/domains/retail/db.json"),
    Path("data/tau2/domains/retail/policy.md"),
    Path("src/tau2/domains/retail/environment.py"),
    Path("src/tau2/domains/retail/tools.py"),
)


def project_root() -> Path:
    """Return this project's repository root."""

    return Path(__file__).resolve().parents[3]


def default_manifest_path() -> Path:
    """Return the committed Day 2 task manifest path."""

    return project_root() / "benchmarks" / "retail_day2_tasks.json"


def _is_tau2_root(path: Path) -> bool:
    return path.is_dir() and all((path / required).is_file() for required in REQUIRED_TAU2_PATHS)


def locate_tau2_root(explicit_root: str | Path | None = None) -> Path:
    """Locate a complete official τ-bench checkout.

    Resolution order is an explicit argument, ``TAU2_BENCH_ROOT``, then the
    two directory names produced by Git clone and GitHub ZIP extraction.
    """

    candidates: list[Path] = []
    if explicit_root is not None:
        candidates.append(Path(explicit_root))
    env_root = os.getenv("TAU2_BENCH_ROOT")
    if env_root:
        candidates.append(Path(env_root))
    external = project_root() / ".external"
    candidates.extend((external / "tau2-bench", external / "tau2-bench-main"))

    checked: list[str] = []
    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        checked.append(str(resolved))
        if _is_tau2_root(resolved):
            return resolved

    locations = "\n- ".join(checked) if checked else "(none)"
    raise FileNotFoundError("No complete τ-bench checkout was found. Checked:\n- " + locations)


def load_manifest(path: str | Path | None = None) -> TaskSubsetManifest:
    """Load and validate the fixed task subset manifest."""

    manifest_path = Path(path) if path is not None else default_manifest_path()
    with manifest_path.open("r", encoding="utf-8") as file:
        return TaskSubsetManifest.model_validate(json.load(file))


def load_official_retail_data(
    tau2_root: Path,
) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]]]:
    """Load official Retail tasks and split definitions."""

    data_root = tau2_root / "data" / "tau2" / "domains" / "retail"
    with (data_root / "tasks.json").open("r", encoding="utf-8") as file:
        raw_tasks = json.load(file)
    with (data_root / "split_tasks.json").open("r", encoding="utf-8") as file:
        splits = json.load(file)
    return {str(task["id"]): task for task in raw_tasks}, splits


def read_tau2_version(tau2_root: Path) -> str:
    """Read the official package version from its pyproject file."""

    with (tau2_root / "pyproject.toml").open("rb") as file:
        metadata = tomllib.load(file)
    return str(metadata["project"]["version"])


def validate_subset(
    manifest: TaskSubsetManifest,
    official_tasks: dict[str, dict[str, Any]],
    splits: dict[str, list[str]],
    *,
    benchmark_version: str,
    official_root: str,
) -> SubsetValidationReport:
    """Validate IDs, split membership, intent labels, and reference write tools."""

    summaries: list[OfficialTaskSummary] = []
    for selection in manifest.tasks:
        try:
            task = official_tasks[selection.task_id]
        except KeyError as error:
            raise ValueError(
                f"task {selection.task_id} is absent from the official Retail task set"
            ) from error

        if selection.task_id not in splits.get("base", []):
            raise ValueError(f"task {selection.task_id} is not in the official base split")
        if selection.task_id not in splits.get(selection.split, []):
            raise ValueError(f"task {selection.task_id} is not in declared {selection.split} split")

        criteria = task.get("evaluation_criteria") or {}
        actions = criteria.get("actions") or []
        action_names = [str(action.get("name")) for action in actions]
        expected_write = WRITE_TOOL_BY_INTENT[selection.intent]
        selected_writes = [name for name in action_names if name in RETAIL_WRITE_TOOLS]
        if selected_writes != [expected_write]:
            raise ValueError(
                f"task {selection.task_id} must contain exactly one {expected_write} "
                f"reference write; found {selected_writes}"
            )

        instructions = task["user_scenario"]["instructions"]
        summaries.append(
            OfficialTaskSummary(
                task_id=selection.task_id,
                intent=selection.intent,
                split=selection.split,
                reason_for_call=instructions["reason_for_call"],
                known_info=instructions.get("known_info"),
                action_names=action_names,
                reward_basis=[str(value) for value in criteria.get("reward_basis", [])],
            )
        )

    counts = Counter(item.intent for item in manifest.tasks)
    return SubsetValidationReport(
        benchmark_version=benchmark_version,
        manifest_name=manifest.name,
        official_root=official_root,
        task_count=len(summaries),
        counts_by_intent=dict(counts),
        tasks=summaries,
    )


def validate_official_subset(
    tau2_root: str | Path | None = None,
    manifest_path: str | Path | None = None,
) -> SubsetValidationReport:
    """Locate the official checkout and validate the committed subset."""

    root = locate_tau2_root(tau2_root)
    manifest = load_manifest(manifest_path)
    official_tasks, splits = load_official_retail_data(root)
    return validate_subset(
        manifest,
        official_tasks,
        splits,
        benchmark_version=read_tau2_version(root),
        official_root=str(root),
    )

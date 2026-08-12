"""Offline deterministic architecture comparison for the Day 8 experiment."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path

from after_sales_agents.benchmark.experiment_models import (
    ArchitectureMetrics,
    ExperimentArchitecture,
    ExperimentMetrics,
    ExperimentOutcome,
    ExperimentReport,
    ExperimentRunResult,
    ExperimentTask,
    ExperimentTaskManifest,
    FaultType,
    TaskDifficulty,
)
from after_sales_agents.benchmark.models import RetailIntent


def default_experiment_manifest_path() -> Path:
    return Path(__file__).resolve().parents[3] / "benchmarks" / "retail_day8_tasks.json"


def load_experiment_manifest(path: str | Path | None = None) -> ExperimentTaskManifest:
    manifest_path = Path(path) if path is not None else default_experiment_manifest_path()
    with manifest_path.open("r", encoding="utf-8") as file:
        return ExperimentTaskManifest.model_validate(json.load(file))


def _pre_audit_outcome(
    architecture: ExperimentArchitecture,
    task: ExperimentTask,
) -> ExperimentOutcome:
    faults = set(task.faults)
    if FaultType.MISSING_INFORMATION in faults:
        return ExperimentOutcome.NEEDS_CLARIFICATION
    if not task.policy_eligible:
        return ExperimentOutcome.POLICY_REJECTED

    is_single = architecture is ExperimentArchitecture.SINGLE_AGENT
    if is_single:
        if FaultType.MULTIPLE_ORDERS in faults or (
            task.requires_money_movement and task.requires_inventory_movement
        ):
            return ExperimentOutcome.HUMAN_HANDOFF
        return ExperimentOutcome.READY_FOR_APPROVAL

    if faults & {FaultType.POLICY_CONFLICT, FaultType.INVENTORY_UNAVAILABLE}:
        return ExperimentOutcome.POLICY_REJECTED
    if FaultType.DUPLICATE_ACTION in faults:
        return ExperimentOutcome.NEEDS_CLARIFICATION
    return ExperimentOutcome.READY_FOR_APPROVAL


def _actual_outcome(
    architecture: ExperimentArchitecture,
    task: ExperimentTask,
) -> ExperimentOutcome:
    outcome = _pre_audit_outcome(architecture, task)
    faults = set(task.faults)
    if (
        architecture is ExperimentArchitecture.ROUTED_MULTI_AGENT_WITH_AUDIT
        and outcome is ExperimentOutcome.READY_FOR_APPROVAL
        and faults & {FaultType.EVIDENCE_MISMATCH, FaultType.ARGUMENT_MISMATCH}
    ):
        return ExperimentOutcome.HUMAN_HANDOFF
    return outcome


def _route_and_calls(
    architecture: ExperimentArchitecture,
    task: ExperimentTask,
    pre_audit_outcome: ExperimentOutcome,
) -> tuple[str, int, int]:
    reads = task.estimated_read_tool_calls
    if architecture is ExperimentArchitecture.SINGLE_AGENT:
        return "single_agent", 1, reads
    if architecture is ExperimentArchitecture.FIXED_MULTI_AGENT:
        return "fixed_multi_agent", 3, reads + 2

    if FaultType.MISSING_INFORMATION in task.faults:
        route, agent_calls, tool_calls = "clarification", 1, 0
    elif task.difficulty is TaskDifficulty.ROUTINE:
        route, agent_calls, tool_calls = "routed_single_agent", 1, reads
    else:
        route, agent_calls, tool_calls = "routed_multi_agent", 3, reads + 2

    if (
        architecture is ExperimentArchitecture.ROUTED_MULTI_AGENT_WITH_AUDIT
        and pre_audit_outcome is ExperimentOutcome.READY_FOR_APPROVAL
    ):
        route += "_with_audit"
        agent_calls += 1
    return route, agent_calls, tool_calls


def _signature(
    *,
    outcome: ExperimentOutcome,
    policy_violation_count: int,
    human_handoff: bool,
    route: str,
) -> str:
    payload = json.dumps(
        {
            "outcome": outcome,
            "policy_violation_count": policy_violation_count,
            "human_handoff": human_handoff,
            "route": route,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def run_task(
    architecture: ExperimentArchitecture,
    task: ExperimentTask,
    repetition: int,
) -> ExperimentRunResult:
    """Evaluate one scenario without a model, network, or write tool."""

    pre_audit = _pre_audit_outcome(architecture, task)
    actual = _actual_outcome(architecture, task)
    route, agent_calls, tool_calls = _route_and_calls(architecture, task, pre_audit)
    successful = actual is task.expected_outcome
    unsafe_ready = (
        actual is ExperimentOutcome.READY_FOR_APPROVAL
        and task.expected_outcome is not ExperimentOutcome.READY_FOR_APPROVAL
    )
    policy_violations = int(unsafe_ready)
    human_handoff = actual is ExperimentOutcome.HUMAN_HANDOFF
    latency_ms = float(
        5
        + 12 * agent_calls
        + 4 * tool_calls
        + (3 if task.difficulty is TaskDifficulty.COMPLEX else 0)
    )
    notes = ["No write tool is available to the experiment runner."]
    if unsafe_ready:
        notes.append("The architecture allowed an unsafe candidate to reach approval review.")
    if architecture is ExperimentArchitecture.ROUTED_MULTI_AGENT_WITH_AUDIT:
        notes.append("The independent auditor has no business-tool permissions.")

    return ExperimentRunResult(
        architecture=architecture,
        task_id=task.task_id,
        intent=task.intent,
        repetition=repetition,
        route=route,
        actual_outcome=actual,
        expected_outcome=task.expected_outcome,
        successful=successful,
        policy_violation_count=policy_violations,
        human_handoff=human_handoff,
        agent_calls=agent_calls,
        tool_calls=tool_calls,
        latency_ms=latency_ms,
        outcome_signature=_signature(
            outcome=actual,
            policy_violation_count=policy_violations,
            human_handoff=human_handoff,
            route=route,
        ),
        notes=notes,
    )


def _rounded_ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6)


def _metrics(results: list[ExperimentRunResult]) -> ExperimentMetrics:
    run_count = len(results)
    successful = sum(result.successful for result in results)
    violations = sum(result.policy_violation_count for result in results)
    handoffs = sum(result.human_handoff for result in results)
    unauthorized_writes = sum(result.unauthorized_write_count for result in results)
    signatures: dict[str, set[str]] = defaultdict(set)
    for result in results:
        signatures[result.task_id].add(result.outcome_signature)
    consistent = sum(len(values) == 1 for values in signatures.values())
    task_count = len(signatures)
    return ExperimentMetrics(
        run_count=run_count,
        successful_runs=successful,
        success_rate=_rounded_ratio(successful, run_count),
        final_state_accuracy=_rounded_ratio(successful, run_count),
        policy_violation_count=violations,
        policy_violation_rate=_rounded_ratio(violations, run_count),
        unauthorized_write_count=unauthorized_writes,
        human_handoff_count=handoffs,
        human_handoff_rate=_rounded_ratio(handoffs, run_count),
        average_agent_calls=round(sum(result.agent_calls for result in results) / run_count, 3),
        average_tool_calls=round(sum(result.tool_calls for result in results) / run_count, 3),
        average_latency_ms=round(sum(result.latency_ms for result in results) / run_count, 3),
        consistent_task_count=consistent,
        consistency_rate=_rounded_ratio(consistent, task_count),
    )


def run_experiment(
    manifest: ExperimentTaskManifest,
    *,
    repetitions: int = 3,
) -> ExperimentReport:
    """Run the complete four-architecture matrix at least three times per task."""

    if repetitions < 3:
        raise ValueError("every experiment task must be repeated at least three times")

    runs = [
        run_task(architecture, task, repetition)
        for architecture in ExperimentArchitecture
        for task in manifest.tasks
        for repetition in range(1, repetitions + 1)
    ]
    architecture_metrics = []
    for architecture in ExperimentArchitecture:
        architecture_runs = [run for run in runs if run.architecture is architecture]
        architecture_metrics.append(
            ArchitectureMetrics(
                architecture=architecture,
                overall=_metrics(architecture_runs),
                by_intent={
                    intent: _metrics([run for run in architecture_runs if run.intent is intent])
                    for intent in RetailIntent
                },
            )
        )

    manifest_payload = json.dumps(
        manifest.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return ExperimentReport(
        manifest_sha256=hashlib.sha256(manifest_payload.encode("utf-8")).hexdigest(),
        repetitions_per_task=repetitions,
        total_run_count=len(runs),
        model_usage_note=(
            "This run made zero model/API calls. Token fields and model_cost_usd are null "
            "because no usage exists; agent_calls are logical workflow invocations."
        ),
        latency_note=(
            "latency_ms is a deterministic operation-budget proxy for architecture comparison, "
            "not measured wall-clock or model latency."
        ),
        result_scope_note=(
            "Results measure this local deterministic control-flow and fault-injection harness; "
            "they are not LLM quality scores and are not official tau2 benchmark results."
        ),
        manifest_name=manifest.name,
        metrics=architecture_metrics,
        runs=runs,
        caveats=[
            "No network, language model, database mutation, or Retail write tool is used.",
            "Success means the architecture selected the scenario card's safe disposition.",
            "Policy violations are unsafe candidates reaching approval review, not real writes.",
            "Unauthorized-write count is zero because the runner exposes no write capability.",
            "All repeated outcomes should match exactly; the signature excludes repetition ID.",
        ],
    )


def render_markdown(report: ExperimentReport) -> str:
    """Render a compact human-readable companion to the complete JSON report."""

    rows = []
    for item in report.metrics:
        metric = item.overall
        rows.append(
            "| "
            + " | ".join(
                [
                    item.architecture,
                    f"{metric.success_rate:.1%}",
                    str(metric.policy_violation_count),
                    str(metric.unauthorized_write_count),
                    f"{metric.human_handoff_rate:.1%}",
                    f"{metric.average_agent_calls:.2f}",
                    f"{metric.average_tool_calls:.2f}",
                    f"{metric.average_latency_ms:.1f}",
                    f"{metric.consistency_rate:.1%}",
                ]
            )
            + " |"
        )
    return "\n".join(
        [
            "# Day 8 offline architecture experiment",
            "",
            f"- Workload: {report.task_count} tasks × {report.repetitions_per_task} repeats",
            f"- Architectures: {report.architecture_count}",
            f"- Complete runs: {report.total_run_count}",
            f"- Manifest SHA-256: `{report.manifest_sha256}`",
            f"- Experiment code version: `{report.experiment_code_version}`",
            "- Model/API calls: 0",
            "- Real write operations: 0",
            "- Model tokens and cost: null (no usage)",
            "",
            "| Architecture | Success | Policy violations | Unauthorized writes | Human handoff | Avg agent calls | Avg tool calls | Latency proxy (ms) | Consistency |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
            *rows,
            "",
            "## Interpretation boundary",
            "",
            report.result_scope_note,
            "",
            report.latency_note,
            "",
            report.model_usage_note,
            "",
            "The JSON artifact contains every per-task repetition and per-intent breakdown.",
            "",
        ]
    )

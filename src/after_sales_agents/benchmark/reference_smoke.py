"""Reference-action smoke runner for the official τ-bench Retail environment.

This runner deliberately replays evaluation reference actions. It verifies the
adapter, official tools, trajectory serialization, and DB evaluator, but it is
not an autonomous-agent score and must never be compared with an LLM baseline.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from after_sales_agents.benchmark.tau2_adapter import (
    load_manifest,
    validate_official_subset,
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _initialize_environment(environment: Any, task: Any) -> list[Any]:
    initial_state = task.initial_state
    if initial_state is None:
        return []

    history = list(initial_state.message_history or [])
    environment.set_state(
        initialization_data=initial_state.initialization_data,
        initialization_actions=initial_state.initialization_actions,
        message_history=history,
    )
    return history


def _run_task(task: Any, intent: str) -> tuple[dict[str, Any], dict[str, Any]]:
    from tau2.data_model.message import AssistantMessage, ToolCall, UserMessage
    from tau2.domains.retail.environment import get_environment
    from tau2.evaluator.evaluator_env import EnvironmentEvaluator

    started_at = _utc_now()
    started = perf_counter()
    environment = get_environment()
    trajectory = _initialize_environment(environment, task)
    initial_db_hash = environment.get_db_hash()

    instructions = task.user_scenario.instructions
    user_content = "\n".join(
        value for value in (instructions.known_info, instructions.reason_for_call) if value
    )
    trajectory.append(UserMessage.text(user_content))

    tool_events: list[dict[str, Any]] = []
    for index, action in enumerate(task.evaluation_criteria.actions or []):
        call = ToolCall(
            id=f"reference-smoke-{task.id}-{index}",
            name=action.name,
            arguments=action.arguments,
            requestor=action.requestor,
        )
        if action.requestor == "user":
            trajectory.append(UserMessage.text("", tool_calls=[call]))
        else:
            trajectory.append(AssistantMessage.text("", tool_calls=[call]))

        call_started = perf_counter()
        response = environment.get_response(call)
        call_latency = perf_counter() - call_started
        trajectory.append(response)
        tool_events.append(
            {
                "sequence": index,
                "requestor": action.requestor,
                "tool_name": action.name,
                "arguments": action.arguments,
                "response": response.content,
                "error": response.error,
                "latency_seconds": round(call_latency, 6),
            }
        )

    final_message = AssistantMessage.text(
        "Reference-action smoke run completed; this is not a model response."
    )
    trajectory.append(final_message)

    reward_info = EnvironmentEvaluator.calculate_reward(
        environment_constructor=get_environment,
        task=task,
        full_trajectory=trajectory,
        solo_mode=False,
    )
    duration = perf_counter() - started
    db_match = bool(reward_info.db_check and reward_info.db_check.db_match)
    tool_errors = sum(1 for event in tool_events if event["error"])
    # Official reference trajectories may intentionally include a failed lookup
    # followed by recovery (task 38 is one such case). τ-bench correctness is
    # outcome-based, so a reference-tool error remains diagnostic and does not
    # override an official final-state match.
    passed = db_match

    result = {
        "task_id": task.id,
        "intent": intent,
        "passed": passed,
        "environment_reward": reward_info.reward,
        "db_match": db_match,
        "tool_call_count": len(tool_events),
        "tool_error_count": tool_errors,
        "latency_seconds": round(duration, 6),
        "agent_model_calls": 0,
        "agent_tokens": None,
        "agent_cost": 0.0,
        "initial_db_hash": initial_db_hash,
        "final_db_hash": environment.get_db_hash(),
        "started_at": started_at,
        "finished_at": _utc_now(),
    }
    trace = {
        "metadata": {
            "task_id": task.id,
            "intent": intent,
            "mode": "reference_action_smoke",
            "uses_evaluation_reference_actions": True,
            "comparable_to_llm_baseline": False,
        },
        "user_scenario": task.user_scenario.model_dump(mode="json"),
        "tool_events": tool_events,
        "final_state": {
            "initial_db_hash": initial_db_hash,
            "final_db_hash": environment.get_db_hash(),
            "official_db_match": db_match,
        },
        "messages": [message.model_dump(mode="json") for message in trajectory],
        "metrics": result,
    }
    return result, trace


def run_reference_smoke(
    output_dir: str | Path,
    tau2_root: str | Path | None = None,
) -> dict[str, Any]:
    """Run the fixed subset through real Retail tools and the official DB evaluator."""

    from loguru import logger

    logger.remove()
    logger.add(sys.stderr, level="WARNING")

    validation = validate_official_subset(tau2_root=tau2_root)
    manifest = load_manifest()

    # Imported lazily so adapter-only commands still work without τ-bench installed.
    from tau2.domains.retail.environment import get_tasks

    official_tasks = {task.id: task for task in get_tasks(task_split_name="base")}
    output_path = Path(output_dir)
    trace_dir = output_path / "traces"
    trace_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    for selection in manifest.tasks:
        result, trace = _run_task(
            official_tasks[selection.task_id],
            selection.intent.value,
        )
        results.append(result)
        trace_file = trace_dir / f"task_{selection.task_id}.json"
        trace_file.write_text(
            json.dumps(trace, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    passed = sum(1 for result in results if result["passed"])
    total_tool_calls = sum(result["tool_call_count"] for result in results)
    total_latency = sum(result["latency_seconds"] for result in results)
    report = {
        "benchmark": "tau2",
        "benchmark_version": validation.benchmark_version,
        "domain": "retail",
        "manifest_name": manifest.name,
        "mode": "reference_action_smoke",
        "generated_at": _utc_now(),
        "task_count": len(results),
        "passed_task_count": passed,
        "environment_pass_rate": passed / len(results),
        "total_tool_calls": total_tool_calls,
        "mean_latency_seconds": total_latency / len(results),
        "agent_model_calls": 0,
        "agent_tokens": None,
        "agent_cost": 0.0,
        "comparable_to_llm_baseline": False,
        "limitations": [
            "Evaluation reference actions are replayed, so this is an integration smoke test, not an autonomous-agent score.",
            "No LLM or user simulator is called; token usage is therefore null and model cost is zero.",
            "Only the official deterministic DB evaluator is run; NL assertions are not evaluated.",
            "Reference tool errors are retained as diagnostics because some official trajectories intentionally recover from failed lookups.",
        ],
        "tasks": results,
    }
    output_path.mkdir(parents=True, exist_ok=True)
    (output_path / "reference_smoke_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report

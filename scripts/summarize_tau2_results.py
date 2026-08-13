"""Build an offline JSON and Markdown summary from official tau2 results."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from numbers import Real
from pathlib import Path
from typing import Any

INFRASTRUCTURE_ERROR = "infrastructure_error"
SESSION_USAGE_METERS = (
    "input_tokens",
    "output_tokens",
    "input_text_tokens",
    "input_audio_tokens",
    "input_cached_tokens",
    "input_cached_text_tokens",
    "input_cached_audio_tokens",
    "output_text_tokens",
    "output_audio_tokens",
    "audio_input_seconds",
    "characters",
)


def _id_sort_key(value: str) -> tuple[int, int | str]:
    try:
        return (0, int(value))
    except ValueError:
        return (1, value)


def _numeric(value: object) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool)


def _reward(simulation: dict[str, Any]) -> int | float | None:
    reward_info = simulation.get("reward_info")
    if not isinstance(reward_info, dict):
        return None
    reward = reward_info.get("reward")
    return reward if _numeric(reward) else None


def _summarize_cost(simulations: list[dict[str, Any]], field: str) -> dict[str, Any]:
    values = [simulation.get(field) for simulation in simulations]
    recorded = [float(value) for value in values if _numeric(value)]
    return {
        "sum_recorded": sum(recorded) if recorded else None,
        "simulations_with_value": len(recorded),
        "simulations_missing_value": len(simulations) - len(recorded),
        "complete": len(recorded) == len(simulations),
    }


def _summarize_message_usage(simulations: list[dict[str, Any]], role: str) -> dict[str, Any]:
    totals: Counter[str] = Counter()
    simulations_with_usage = 0
    messages_with_usage = 0

    for simulation in simulations:
        found_in_simulation = False
        messages = simulation.get("messages")
        if not isinstance(messages, list):
            continue
        for message in messages:
            if not isinstance(message, dict) or message.get("role") != role:
                continue
            usage = message.get("usage")
            if not isinstance(usage, dict):
                continue
            numeric_usage = {
                key: value
                for key, value in usage.items()
                if isinstance(key, str) and _numeric(value)
            }
            if not numeric_usage:
                continue
            found_in_simulation = True
            messages_with_usage += 1
            totals.update(numeric_usage)
        if found_in_simulation:
            simulations_with_usage += 1

    return {
        "source": "messages[].usage",
        "totals": dict(sorted(totals.items())),
        "simulations_with_usage": simulations_with_usage,
        "simulations_missing_usage": len(simulations) - simulations_with_usage,
        "messages_with_usage": messages_with_usage,
    }


def _summarize_agent_session_usage(
    simulations: list[dict[str, Any]],
) -> dict[str, Any]:
    totals: Counter[str] = Counter()
    simulations_with_usage = 0
    records_with_usage = 0

    for simulation in simulations:
        session_usage = simulation.get("agent_usage")
        if not isinstance(session_usage, dict):
            continue
        records = session_usage.get("records")
        if not isinstance(records, list):
            continue
        found_in_simulation = False
        for record in records:
            if not isinstance(record, dict):
                continue
            numeric_usage = {
                meter: record[meter]
                for meter in SESSION_USAGE_METERS
                if _numeric(record.get(meter))
            }
            if not numeric_usage:
                continue
            found_in_simulation = True
            records_with_usage += 1
            totals.update(numeric_usage)
        if found_in_simulation:
            simulations_with_usage += 1

    return {
        "source": "agent_usage.records[]",
        "totals": dict(sorted(totals.items())),
        "simulations_with_usage": simulations_with_usage,
        "simulations_missing_usage": len(simulations) - simulations_with_usage,
        "records_with_usage": records_with_usage,
    }


def _coverage(
    payload: dict[str, Any], simulations: list[dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, Any]]:
    tasks = payload.get("tasks")
    expected_task_ids = (
        {str(task["id"]) for task in tasks if isinstance(task, dict) and task.get("id") is not None}
        if isinstance(tasks, list)
        else set()
    )
    observed_task_ids = {
        str(simulation["task_id"])
        for simulation in simulations
        if simulation.get("task_id") is not None
    }
    missing_task_ids = sorted(expected_task_ids - observed_task_ids, key=_id_sort_key)
    unexpected_task_ids = sorted(observed_task_ids - expected_task_ids, key=_id_sort_key)
    task_coverage = {
        "expected_count": len(expected_task_ids),
        "observed_count": len(observed_task_ids),
        "missing_count": len(missing_task_ids),
        "unexpected_count": len(unexpected_task_ids),
        "missing_task_ids": missing_task_ids,
        "unexpected_task_ids": unexpected_task_ids,
        "complete": not missing_task_ids and not unexpected_task_ids,
    }

    info = payload.get("info")
    num_trials = info.get("num_trials") if isinstance(info, dict) else None
    expected_trials = num_trials if isinstance(num_trials, int) and num_trials >= 0 else None
    observed_pairs: Counter[tuple[str, int | None]] = Counter()
    observed_trial_ids: set[int] = set()
    for simulation in simulations:
        task_id = simulation.get("task_id")
        if task_id is None:
            continue
        trial = simulation.get("trial")
        normalized_trial = trial if isinstance(trial, int) and not isinstance(trial, bool) else None
        observed_pairs[(str(task_id), normalized_trial)] += 1
        if normalized_trial is not None:
            observed_trial_ids.add(normalized_trial)

    missing_pairs: list[dict[str, Any]] = []
    unexpected_pairs: list[dict[str, Any]] = []
    if expected_trials is not None:
        expected_pairs = {
            (task_id, trial) for task_id in expected_task_ids for trial in range(expected_trials)
        }
        for task_id, trial in sorted(
            expected_pairs - observed_pairs.keys(),
            key=lambda item: (_id_sort_key(item[0]), item[1]),
        ):
            missing_pairs.append({"task_id": task_id, "trial": trial})
        for task_id, trial in sorted(
            observed_pairs.keys() - expected_pairs,
            key=lambda item: (_id_sort_key(item[0]), -1 if item[1] is None else item[1]),
        ):
            unexpected_pairs.append({"task_id": task_id, "trial": trial})

    duplicate_pairs = [
        {"task_id": task_id, "trial": trial, "count": count}
        for (task_id, trial), count in sorted(
            observed_pairs.items(),
            key=lambda item: (_id_sort_key(item[0][0]), -1 if item[0][1] is None else item[0][1]),
        )
        if count > 1
    ]
    expected_simulation_count = (
        len(expected_task_ids) * expected_trials if expected_trials is not None else None
    )
    trial_coverage = {
        "expected_trials_per_task": expected_trials,
        "observed_trial_ids": sorted(observed_trial_ids),
        "expected_simulation_count": expected_simulation_count,
        "observed_unique_task_trials": len(observed_pairs),
        "missing_count": len(missing_pairs) if expected_trials is not None else None,
        "unexpected_count": len(unexpected_pairs) if expected_trials is not None else None,
        "duplicate_count": len(duplicate_pairs),
        "missing_task_trials": missing_pairs,
        "unexpected_task_trials": unexpected_pairs,
        "duplicate_task_trials": duplicate_pairs,
        "complete": (
            expected_trials is not None
            and not missing_pairs
            and not unexpected_pairs
            and not duplicate_pairs
        ),
    }
    return task_coverage, trial_coverage


def summarize_results(payload: dict[str, Any]) -> dict[str, Any]:
    """Summarize official results without invoking any model or evaluator."""

    raw_simulations = payload.get("simulations")
    if not isinstance(raw_simulations, list):
        raise TypeError("results.json field 'simulations' must be a list")
    if not all(isinstance(simulation, dict) for simulation in raw_simulations):
        raise ValueError("every simulations entry must be an object")
    simulations: list[dict[str, Any]] = raw_simulations

    termination_counts = Counter(
        str(simulation.get("termination_reason") or "missing") for simulation in simulations
    )
    infrastructure_errors = [
        simulation
        for simulation in simulations
        if simulation.get("termination_reason") == INFRASTRUCTURE_ERROR
    ]
    scored = [
        simulation
        for simulation in simulations
        if simulation.get("termination_reason") != INFRASTRUCTURE_ERROR
        and _reward(simulation) is not None
    ]
    passed = [simulation for simulation in scored if _reward(simulation) == 1]
    failed = [simulation for simulation in scored if _reward(simulation) != 1]
    other_unscored = len(simulations) - len(infrastructure_errors) - len(scored)
    task_coverage, trial_coverage = _coverage(payload, simulations)
    agent_cost = _summarize_cost(simulations, "agent_cost")
    user_cost = _summarize_cost(simulations, "user_cost")
    recorded_costs = [
        simulation.get(field)
        for simulation in simulations
        for field in ("agent_cost", "user_cost")
        if _numeric(simulation.get(field))
    ]

    return {
        "counts": {
            "total": len(simulations),
            "scored": len(scored),
            "pass": len(passed),
            "fail": len(failed),
            "infrastructure_error": len(infrastructure_errors),
            "other_unscored": other_unscored,
        },
        "pass_rate_scored": len(passed) / len(scored) if scored else None,
        "termination_counts": dict(sorted(termination_counts.items())),
        "task_coverage": task_coverage,
        "trial_coverage": trial_coverage,
        "cost": {
            "currency": None,
            "agent": agent_cost,
            "user": user_cost,
            "combined_sum_recorded": (
                sum(float(value) for value in recorded_costs) if recorded_costs else None
            ),
            "note": "The results file does not declare a currency; no currency is assumed.",
        },
        "usage": {
            "agent": {
                "message_usage": _summarize_message_usage(simulations, "assistant"),
                "session_usage": _summarize_agent_session_usage(simulations),
            },
            "user": {"message_usage": _summarize_message_usage(simulations, "user")},
        },
    }


def _format_value(value: object) -> str:
    return "not reported" if value is None else str(value)


def render_markdown(summary: dict[str, Any], *, source: str | None = None) -> str:
    """Render the machine-readable summary as a compact Markdown report."""

    counts = summary["counts"]
    task_coverage = summary["task_coverage"]
    trial_coverage = summary["trial_coverage"]
    cost = summary["cost"]
    usage = summary["usage"]
    pass_rate = summary["pass_rate_scored"]
    lines = ["# tau2 results summary", ""]
    if source:
        lines.extend([f"Source: `{source}`", ""])
    lines.extend(
        [
            "## Score",
            "",
            f"- Total: {counts['total']}",
            f"- Scored: {counts['scored']}",
            f"- Pass: {counts['pass']}",
            f"- Fail: {counts['fail']}",
            f"- Infrastructure error: {counts['infrastructure_error']}",
            f"- Other unscored: {counts['other_unscored']}",
            f"- Pass rate (scored only): {pass_rate:.2%}"
            if pass_rate is not None
            else "- Pass rate (scored only): not available",
            "",
            "## Terminations",
            "",
            "| Reason | Count |",
            "| --- | ---: |",
        ]
    )
    for reason, count in summary["termination_counts"].items():
        lines.append(f"| {reason} | {count} |")
    lines.extend(
        [
            "",
            "## Coverage",
            "",
            (
                f"- Tasks: {task_coverage['observed_count']}/{task_coverage['expected_count']} "
                f"observed; missing {task_coverage['missing_count']}; "
                f"unexpected {task_coverage['unexpected_count']}"
            ),
            (
                f"- Task/trials: {trial_coverage['observed_unique_task_trials']}/"
                f"{_format_value(trial_coverage['expected_simulation_count'])} unique pairs; "
                f"missing {_format_value(trial_coverage['missing_count'])}; "
                f"unexpected {_format_value(trial_coverage['unexpected_count'])}; "
                f"duplicates {trial_coverage['duplicate_count']}"
            ),
            f"- Observed trial IDs: {trial_coverage['observed_trial_ids']}",
        ]
    )
    if task_coverage["missing_task_ids"]:
        lines.append(f"- Missing task IDs: {task_coverage['missing_task_ids']}")
    if task_coverage["unexpected_task_ids"]:
        lines.append(f"- Unexpected task IDs: {task_coverage['unexpected_task_ids']}")

    lines.extend(["", "## Cost and usage", ""])
    lines.append("Cost currency is not declared by the results file; values remain unitless.")
    lines.extend(
        [
            "",
            "| Side | Recorded cost sum | Simulations with cost | Prompt tokens | Completion tokens |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for side in ("agent", "user"):
        side_cost = cost[side]
        side_usage = usage[side]["message_usage"]
        totals = side_usage["totals"]
        lines.append(
            f"| {side.title()} | {_format_value(side_cost['sum_recorded'])} | "
            f"{side_cost['simulations_with_value']}/{counts['total']} | "
            f"{_format_value(totals.get('prompt_tokens'))} | "
            f"{_format_value(totals.get('completion_tokens'))} |"
        )
    session_totals = usage["agent"]["session_usage"]["totals"]
    if session_totals:
        lines.extend(
            [
                "",
                "Agent session usage reported by `agent_usage.records[]`:",
                "",
                "| Meter | Total |",
                "| --- | ---: |",
            ]
        )
        for meter, total in session_totals.items():
            lines.append(f"| {meter} | {total} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path, help="Official tau2 results.json")
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    args = parser.parse_args()

    result_path = args.result.resolve()
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    summary = summarize_results(payload)
    markdown = render_markdown(summary, source=str(result_path))

    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if args.markdown_output:
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(markdown, encoding="utf-8")
    if not args.json_output and not args.markdown_output:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

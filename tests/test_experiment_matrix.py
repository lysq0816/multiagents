import json
from collections import Counter

import pytest

from after_sales_agents.benchmark.experiment_matrix import (
    load_experiment_manifest,
    render_markdown,
    run_experiment,
    run_task,
)
from after_sales_agents.benchmark.experiment_models import (
    ExperimentArchitecture,
    ExperimentOutcome,
)
from after_sales_agents.benchmark.models import RetailIntent


def test_manifest_has_thirty_balanced_tasks() -> None:
    manifest = load_experiment_manifest()

    assert len(manifest.tasks) == 30
    assert Counter(task.intent for task in manifest.tasks) == {
        RetailIntent.CANCEL: 10,
        RetailIntent.RETURN: 10,
        RetailIntent.EXCHANGE: 10,
    }
    assert len({task.task_id for task in manifest.tasks}) == 30


def test_complete_matrix_has_three_repeats_and_four_architectures() -> None:
    report = run_experiment(load_experiment_manifest())

    assert report.total_run_count == 30 * 3 * 4 == 360
    assert len(report.manifest_sha256) == 64
    assert report.experiment_code_version == "day8-v1"
    assert Counter(run.architecture for run in report.runs) == {
        architecture: 90 for architecture in ExperimentArchitecture
    }
    repetition_counts = Counter((run.architecture, run.task_id) for run in report.runs)
    assert len(repetition_counts) == 120
    assert set(repetition_counts.values()) == {3}


def test_repetitions_below_three_are_rejected() -> None:
    with pytest.raises(ValueError, match="at least three"):
        run_experiment(load_experiment_manifest(), repetitions=2)


def test_runs_are_deterministic_per_architecture_and_task() -> None:
    report = run_experiment(load_experiment_manifest())
    grouped: dict[tuple[ExperimentArchitecture, str], set[str]] = {}
    for run in report.runs:
        grouped.setdefault((run.architecture, run.task_id), set()).add(run.outcome_signature)

    assert all(len(signatures) == 1 for signatures in grouped.values())
    assert all(metric.overall.consistency_rate == 1.0 for metric in report.metrics)


def test_zero_model_usage_is_not_replaced_with_fake_token_or_cost_values() -> None:
    report = run_experiment(load_experiment_manifest())

    assert all(run.model_calls == 0 for run in report.runs)
    assert all(run.total_tokens is None and run.model_cost_usd is None for run in report.runs)
    assert all(
        metric.overall.total_tokens is None and metric.overall.model_cost_usd is None
        for metric in report.metrics
    )
    assert "null" in report.model_usage_note


def test_experiment_never_performs_or_reports_an_unauthorized_write() -> None:
    report = run_experiment(load_experiment_manifest())

    assert report.real_write_operations == 0
    assert sum(run.unauthorized_write_count for run in report.runs) == 0
    assert all(metric.overall.unauthorized_write_count == 0 for metric in report.metrics)


def test_audit_catches_evidence_and_argument_faults() -> None:
    manifest = load_experiment_manifest()
    for task_id in ("C06", "C07", "R06", "R07", "E06", "E07"):
        task = next(task for task in manifest.tasks if task.task_id == task_id)
        without_audit = run_task(ExperimentArchitecture.ROUTED_MULTI_AGENT, task, 1)
        with_audit = run_task(ExperimentArchitecture.ROUTED_MULTI_AGENT_WITH_AUDIT, task, 1)

        assert without_audit.actual_outcome is ExperimentOutcome.READY_FOR_APPROVAL
        assert without_audit.policy_violation_count == 1
        assert with_audit.actual_outcome is ExperimentOutcome.HUMAN_HANDOFF
        assert with_audit.policy_violation_count == 0


def test_routing_avoids_unnecessary_multi_agent_calls_for_routine_tasks() -> None:
    task = next(task for task in load_experiment_manifest().tasks if task.task_id == "C01")
    fixed = run_task(ExperimentArchitecture.FIXED_MULTI_AGENT, task, 1)
    routed = run_task(ExperimentArchitecture.ROUTED_MULTI_AGENT, task, 1)

    assert routed.agent_calls < fixed.agent_calls
    assert routed.tool_calls < fixed.tool_calls


def test_report_supports_json_round_trip_and_markdown_summary() -> None:
    report = run_experiment(load_experiment_manifest())
    payload = json.loads(report.model_dump_json())
    markdown = render_markdown(report)

    assert payload["total_run_count"] == 360
    assert "single_agent" in markdown
    assert "Model/API calls: 0" in markdown
    assert "not LLM quality scores" in markdown

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "summarize_tau2_results.py"
SPEC = importlib.util.spec_from_file_location("summarize_tau2_results", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _payload() -> dict[str, object]:
    return {
        "info": {"num_trials": 2},
        "tasks": [{"id": "0"}, {"id": "1"}],
        "simulations": [
            {
                "task_id": "0",
                "trial": 0,
                "termination_reason": "user_stop",
                "reward_info": {"reward": 1.0},
                "agent_cost": 0.1,
                "user_cost": 0.01,
                "agent_usage": {
                    "records": [
                        {
                            "provider": "example",
                            "input_audio_tokens": 7,
                            "output_audio_tokens": 5,
                        }
                    ]
                },
                "messages": [
                    {
                        "role": "assistant",
                        "usage": {"prompt_tokens": 10, "completion_tokens": 2},
                    },
                    {
                        "role": "user",
                        "usage": {"prompt_tokens": 3, "completion_tokens": 1},
                    },
                ],
            },
            {
                "task_id": "0",
                "trial": 1,
                "termination_reason": "agent_stop",
                "reward_info": {"reward": 0.0},
                "agent_cost": 0.2,
                "user_cost": None,
                "messages": [
                    {
                        "role": "assistant",
                        "usage": {"prompt_tokens": 20, "completion_tokens": 4},
                    }
                ],
            },
            {
                "task_id": "1",
                "trial": 0,
                "termination_reason": "infrastructure_error",
                "reward_info": {"reward": 1.0},
                "agent_cost": None,
                "user_cost": None,
                "messages": [],
            },
        ],
    }


def test_summary_separates_scores_infrastructure_and_missing_trial() -> None:
    summary = MODULE.summarize_results(_payload())

    assert summary["counts"] == {
        "total": 3,
        "scored": 2,
        "pass": 1,
        "fail": 1,
        "infrastructure_error": 1,
        "other_unscored": 0,
    }
    assert summary["pass_rate_scored"] == 0.5
    assert summary["termination_counts"] == {
        "agent_stop": 1,
        "infrastructure_error": 1,
        "user_stop": 1,
    }
    assert summary["task_coverage"]["complete"] is True
    assert summary["trial_coverage"]["missing_task_trials"] == [{"task_id": "1", "trial": 1}]
    assert summary["trial_coverage"]["complete"] is False


def test_summary_aggregates_only_reported_cost_and_message_usage() -> None:
    summary = MODULE.summarize_results(_payload())

    assert summary["cost"]["currency"] is None
    assert summary["cost"]["agent"]["sum_recorded"] == pytest.approx(0.3)
    assert summary["cost"]["agent"]["simulations_with_value"] == 2
    assert summary["cost"]["agent"]["complete"] is False
    assert summary["cost"]["user"]["sum_recorded"] == pytest.approx(0.01)
    assert summary["usage"]["agent"]["message_usage"]["totals"] == {
        "completion_tokens": 6,
        "prompt_tokens": 30,
    }
    assert summary["usage"]["agent"]["session_usage"]["totals"] == {
        "input_audio_tokens": 7,
        "output_audio_tokens": 5,
    }
    assert summary["usage"]["user"]["message_usage"]["totals"] == {
        "completion_tokens": 1,
        "prompt_tokens": 3,
    }


def test_other_unscored_is_not_counted_as_fail() -> None:
    payload = {
        "info": {"num_trials": 1},
        "tasks": [{"id": "0"}],
        "simulations": [
            {
                "task_id": "0",
                "trial": 0,
                "termination_reason": "unexpected_error",
                "reward_info": None,
            }
        ],
    }

    summary = MODULE.summarize_results(payload)

    assert summary["counts"]["scored"] == 0
    assert summary["counts"]["fail"] == 0
    assert summary["counts"]["other_unscored"] == 1
    assert summary["pass_rate_scored"] is None


def test_markdown_mentions_scored_denominator_and_unitless_cost() -> None:
    markdown = MODULE.render_markdown(MODULE.summarize_results(_payload()))

    assert "Pass rate (scored only): 50.00%" in markdown
    assert "Cost currency is not declared" in markdown
    assert "| Agent |" in markdown
    assert "| input_audio_tokens | 7 |" in markdown

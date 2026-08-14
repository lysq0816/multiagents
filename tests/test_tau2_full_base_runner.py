from __future__ import annotations

import importlib.util
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_tau2_llm_baseline.py"
SPEC = importlib.util.spec_from_file_location("run_tau2_llm_baseline", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_full_base_command_omits_task_ids() -> None:
    tau2_root = PROJECT_ROOT / ".external" / "tau2-bench-main"

    command = MODULE.build_command(
        tau2_root,
        agent_model="deepseek/test",
        user_model="deepseek/test",
        save_to="full-base-test",
        num_trials=1,
        task_ids=None,
        enforce_communication_protocol=False,
    )

    assert "--task-split-name" in command
    assert command[command.index("--task-split-name") + 1] == "base"
    assert "--task-ids" not in command


def test_subset_command_keeps_explicit_task_ids() -> None:
    tau2_root = PROJECT_ROOT / ".external" / "tau2-bench-main"

    command = MODULE.build_command(
        tau2_root,
        agent_model="deepseek/test",
        user_model="deepseek/test",
        save_to="subset-test",
        num_trials=1,
        task_ids=["38", "70"],
        enforce_communication_protocol=False,
    )

    index = command.index("--task-ids")
    assert command[index + 1 : index + 3] == ["38", "70"]


def test_result_completeness_counts_trials_and_rejects_unscored_entries() -> None:
    payload = {
        "simulations": [
            {
                "task_id": "0",
                "trial": 0,
                "termination_reason": "user_stop",
                "reward_info": {"reward": 1},
            },
            {
                "task_id": "0",
                "trial": 1,
                "termination_reason": "infrastructure_error",
                "reward_info": None,
            },
        ]
    }

    actual_count, unscored = MODULE.assess_result_completeness(
        payload,
        expected_simulation_count=2,
    )

    assert actual_count == 2
    assert unscored == [
        {
            "task_id": "0",
            "trial": 1,
            "termination_reason": "infrastructure_error",
        }
    ]


def test_auto_resume_is_explicitly_forwarded_to_official_runner() -> None:
    tau2_root = PROJECT_ROOT / ".external" / "tau2-bench-main"

    command = MODULE.build_command(
        tau2_root,
        agent_model="deepseek/test",
        user_model="deepseek/test",
        save_to="resume-test",
        num_trials=1,
        task_ids=None,
        enforce_communication_protocol=False,
        auto_resume=True,
    )

    assert command[-1] == "--auto-resume"


def test_max_concurrency_is_forwarded_to_official_runner() -> None:
    tau2_root = PROJECT_ROOT / ".external" / "tau2-bench-main"

    command = MODULE.build_command(
        tau2_root,
        agent_model="deepseek/test",
        user_model="deepseek/test",
        save_to="concurrency-test",
        num_trials=4,
        task_ids=None,
        enforce_communication_protocol=False,
        auto_resume=True,
        max_concurrency=3,
    )

    index = command.index("--max-concurrency")
    assert command[index + 1] == "3"


def test_result_completeness_rejects_duplicate_task_trials() -> None:
    simulation = {
        "task_id": "0",
        "trial": 0,
        "termination_reason": "user_stop",
        "reward_info": {"reward": 1},
    }

    actual_count, incomplete = MODULE.assess_result_completeness(
        {"simulations": [simulation, simulation.copy()]},
        expected_simulation_count=2,
    )

    assert actual_count == 2
    assert incomplete == [{"reason": "duplicate_task_trial", "task_id": "0", "trial": 0}]


def test_trial_metadata_is_normalized_after_validated_checkpoint_expansion() -> None:
    payload = {"info": {"num_trials": 1}, "simulations": []}

    source_num_trials = MODULE.normalize_result_trial_metadata(
        payload,
        expected_num_trials=4,
    )

    assert source_num_trials == 1
    assert payload["info"]["num_trials"] == 4

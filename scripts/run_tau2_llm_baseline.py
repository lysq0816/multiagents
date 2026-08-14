"""Prepare or execute the real τ-bench single-LLM Retail baseline."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from after_sales_agents.benchmark.tau2_adapter import (
    load_manifest,
    load_official_retail_data,
    locate_tau2_root,
)
from after_sales_agents.benchmark.tau2_runtime import (
    AGENT_INSTRUCTION_PROFILES,
    MULTI_AGENT_IMPLEMENTATION,
    OFFICIAL_AGENT_IMPLEMENTATION,
    OFFICIAL_AGENT_INSTRUCTION_PROFILE,
    build_subprocess_environment,
)
from after_sales_agents.model_credentials import load_model_credentials


def _tau2_python(tau2_root: Path) -> Path:
    windows_executable = tau2_root / ".venv" / "Scripts" / "python.exe"
    unix_executable = tau2_root / ".venv" / "bin" / "python"
    for candidate in (windows_executable, unix_executable):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "τ-bench virtual environment not found; run `uv sync --no-dev` in its root"
    )


def build_command(
    tau2_root: Path,
    *,
    agent_model: str,
    user_model: str,
    save_to: str,
    num_trials: int,
    task_ids: list[str] | None,
    enforce_communication_protocol: bool,
    agent_implementation: str = OFFICIAL_AGENT_IMPLEMENTATION,
    auto_resume: bool = False,
    max_concurrency: int = 1,
    model_request_timeout: float | None = None,
) -> list[str]:
    """Build a deterministic official CLI command for a subset or the full base split."""

    llm_args: dict[str, float] = {"temperature": 0.0}
    if model_request_timeout is not None:
        llm_args["timeout"] = model_request_timeout
    serialized_llm_args = json.dumps(llm_args)

    command = [
        str(_tau2_python(tau2_root)),
        str(PROJECT_ROOT / "scripts" / "tau2_with_model_overrides.py"),
        "run",
        "--domain",
        "retail",
        "--agent",
        agent_implementation,
        "--agent-llm",
        agent_model,
        "--agent-llm-args",
        serialized_llm_args,
        "--user",
        "user_simulator",
        "--user-llm",
        user_model,
        "--user-llm-args",
        serialized_llm_args,
        "--task-split-name",
        "base",
        "--num-trials",
        str(num_trials),
        "--max-concurrency",
        str(max_concurrency),
        "--max-steps",
        "80",
        "--timeout",
        "300",
        "--seed",
        "300",
        "--save-to",
        save_to,
        "--verbose-logs",
    ]
    if task_ids is not None:
        split_index = command.index("--num-trials")
        command[split_index:split_index] = ["--task-ids", *task_ids]
    if enforce_communication_protocol:
        command.append("--enforce-communication-protocol")
    if auto_resume:
        command.append("--auto-resume")
    return command


def assess_result_completeness(
    source_payload: dict[str, object],
    *,
    expected_simulation_count: int,
    expected_agent_implementation: str | None = None,
    expected_agent_model: str | None = None,
    expected_user_implementation: str | None = None,
    expected_user_model: str | None = None,
    expected_domain: str | None = None,
) -> tuple[int, list[dict[str, object]]]:
    """Return the result count and entries that prevent a complete official run."""

    simulations = source_payload.get("simulations", [])
    if not isinstance(simulations, list):
        return 0, [{"reason": "simulations_not_a_list"}]

    incomplete_simulations = []
    run_keys: set[tuple[object, object]] = set()
    for simulation in simulations:
        if not isinstance(simulation, dict):
            incomplete_simulations.append({"reason": "simulation_not_an_object"})
            continue
        run_key = (simulation.get("task_id"), simulation.get("trial"))
        if run_key in run_keys:
            incomplete_simulations.append(
                {
                    "reason": "duplicate_task_trial",
                    "task_id": run_key[0],
                    "trial": run_key[1],
                }
            )
        run_keys.add(run_key)
        reward_info = simulation.get("reward_info")
        reward = reward_info.get("reward") if isinstance(reward_info, dict) else None
        termination_reason = simulation.get("termination_reason")
        if reward is None or termination_reason == "infrastructure_error":
            incomplete_simulations.append(
                {
                    "task_id": simulation.get("task_id"),
                    "trial": simulation.get("trial"),
                    "termination_reason": termination_reason,
                }
            )

    if len(simulations) != expected_simulation_count:
        incomplete_simulations.append(
            {
                "reason": "unexpected_simulation_count",
                "expected": expected_simulation_count,
                "actual": len(simulations),
            }
        )

    expected_identity = {
        "info.agent_info.implementation": expected_agent_implementation,
        "info.agent_info.llm": expected_agent_model,
        "info.user_info.implementation": expected_user_implementation,
        "info.user_info.llm": expected_user_model,
        "info.environment_info.domain_name": expected_domain,
    }
    for field, expected in expected_identity.items():
        if expected is None:
            continue
        actual: object = source_payload
        for key in field.split("."):
            actual = actual.get(key) if isinstance(actual, dict) else None
        if actual != expected:
            incomplete_simulations.append(
                {
                    "reason": "result_identity_mismatch",
                    "field": field,
                    "expected": expected,
                    "actual": actual,
                }
            )
    return len(simulations), incomplete_simulations


def normalize_result_trial_metadata(
    source_payload: dict[str, object],
    *,
    expected_num_trials: int,
) -> object:
    """Align copied result metadata with the already-validated trial coverage."""

    info = source_payload.get("info")
    if not isinstance(info, dict):
        raise TypeError("Official result payload is missing an info object")
    source_num_trials = info.get("num_trials")
    info["num_trials"] = expected_num_trials
    return source_num_trials


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tau2-root", type=Path)
    parser.add_argument("--agent-model", default="deepseek/deepseek-v4-flash")
    parser.add_argument("--user-model", default="deepseek/deepseek-v4-flash")
    parser.add_argument("--evaluator-model", default="deepseek/deepseek-v4-flash")
    parser.add_argument(
        "--save-to",
        default="after_sales_day2_deepseek_v4_flash_compatible",
    )
    parser.add_argument("--num-trials", type=int, default=1)
    parser.add_argument(
        "--agent-implementation",
        choices=[OFFICIAL_AGENT_IMPLEMENTATION, MULTI_AGENT_IMPLEMENTATION],
        default=OFFICIAL_AGENT_IMPLEMENTATION,
        help="Official single agent or the project difficulty-routed multi-agent runtime.",
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=1,
        help="Number of official tau2 simulations to run concurrently.",
    )
    parser.add_argument(
        "--model-request-timeout",
        type=float,
        help=(
            "Optional LiteLLM timeout in seconds for each agent and user model request. "
            "Use this to turn a stalled provider request into a recoverable run failure."
        ),
    )
    parser.add_argument("--task-ids", nargs="+")
    parser.add_argument(
        "--all-base-tasks",
        action="store_true",
        help=(
            "Evaluate every task in the official Retail base split. This is mutually "
            "exclusive with --task-ids and may incur substantial model cost."
        ),
    )
    parser.add_argument(
        "--agent-instruction-profile",
        choices=sorted(AGENT_INSTRUCTION_PROFILES),
        default=OFFICIAL_AGENT_INSTRUCTION_PROFILE,
        help=(
            "Use the unmodified official τ2 agent prompt by default. The auditable "
            "profile is a diagnostic prompt variant and is not an official baseline."
        ),
    )
    parser.add_argument(
        "--artifact-label",
        help="Safe filename label for launch and result artifacts.",
    )
    parser.add_argument(
        "--enforce-communication-protocol",
        action="store_true",
        help="Reject mixed text plus tool-call messages. Disabled for DeepSeek compatibility.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute the API-backed run. Without this flag, only record a dry run.",
    )
    parser.add_argument(
        "--auto-resume",
        action="store_true",
        help=(
            "Resume the same official save-to checkpoint without prompting. "
            "Infrastructure-error simulations are rerun by the official runner."
        ),
    )
    args = parser.parse_args()

    if args.all_base_tasks and args.task_ids:
        parser.error("--all-base-tasks cannot be combined with --task-ids")
    if args.max_concurrency < 1:
        parser.error("--max-concurrency must be at least 1")
    if args.model_request_timeout is not None and args.model_request_timeout <= 0:
        parser.error("--model-request-timeout must be greater than 0")
    tau2_root = locate_tau2_root(args.tau2_root)
    _, split_tasks = load_official_retail_data(tau2_root)
    base_task_ids = {str(task_id) for task_id in split_tasks.get("base", [])}
    manifest_task_ids = [task.task_id for task in load_manifest().tasks]
    task_ids = None if args.all_base_tasks else (args.task_ids or manifest_task_ids)
    if args.task_ids:
        unknown_task_ids = sorted(set(args.task_ids) - base_task_ids)
        if unknown_task_ids:
            parser.error(f"Task IDs are outside the official Retail base split: {unknown_task_ids}")
    expected_task_count = len(base_task_ids) if args.all_base_tasks else len(task_ids)
    expected_simulation_count = expected_task_count * args.num_trials

    protocol = "strict" if args.enforce_communication_protocol else "compatible"
    artifact_label = args.artifact_label or protocol
    if not artifact_label.replace("-", "").replace("_", "").isalnum():
        parser.error("--artifact-label may contain only letters, numbers, '-' and '_'")

    command = build_command(
        tau2_root,
        agent_model=args.agent_model,
        user_model=args.user_model,
        save_to=args.save_to,
        num_trials=args.num_trials,
        task_ids=task_ids,
        enforce_communication_protocol=args.enforce_communication_protocol,
        agent_implementation=args.agent_implementation,
        auto_resume=args.auto_resume,
        max_concurrency=args.max_concurrency,
        model_request_timeout=args.model_request_timeout,
    )
    configured_keys = load_model_credentials()
    record = {
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": "execute" if args.execute else "dry_run",
        "tau2_root": str(tau2_root),
        "task_ids": task_ids,
        "task_scope": "official_retail_base_all" if args.all_base_tasks else "selected_subset",
        "expected_task_count": expected_task_count,
        "expected_simulation_count": expected_simulation_count,
        "agent_model": args.agent_model,
        "agent_implementation": args.agent_implementation,
        "architecture": (
            "difficulty_routed_multi_agent"
            if args.agent_implementation == MULTI_AGENT_IMPLEMENTATION
            else "single_agent"
        ),
        "user_model": args.user_model,
        "evaluator_model": args.evaluator_model,
        "agent_instruction_profile": args.agent_instruction_profile,
        "official_agent_prompt": (
            args.agent_implementation == OFFICIAL_AGENT_IMPLEMENTATION
            and args.agent_instruction_profile == OFFICIAL_AGENT_INSTRUCTION_PROFILE
        ),
        "num_trials": args.num_trials,
        "max_concurrency": args.max_concurrency,
        "model_request_timeout": args.model_request_timeout,
        "enforce_communication_protocol": args.enforce_communication_protocol,
        "auto_resume": args.auto_resume,
        "deepseek_reasoning_content_replay": any(
            model.lower().startswith("deepseek/") for model in (args.agent_model, args.user_model)
        ),
        "configured_key_names": configured_keys,
        "command": command,
        "status": "prepared" if configured_keys else "prepared_missing_api_key",
    }
    artifact_dir = PROJECT_ROOT / "artifacts" / "day2"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    launch_record = artifact_dir / f"llm_baseline_launch_{artifact_label}.json"

    if not args.execute:
        launch_record.write_text(
            json.dumps(record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(json.dumps(record, ensure_ascii=False, indent=2))
        return 0

    if not configured_keys:
        record["status"] = "blocked_missing_api_key"
        launch_record.write_text(
            json.dumps(record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(
            "No supported model API key is configured. Set the provider key and rerun.",
            file=sys.stderr,
        )
        return 2

    environment = build_subprocess_environment(
        evaluator_model=args.evaluator_model,
        agent_instruction_profile=args.agent_instruction_profile,
        agent_implementation=args.agent_implementation,
        agent_model=args.agent_model,
        user_model=args.user_model,
    )
    completed = subprocess.run(command, cwd=tau2_root, env=environment, check=False)
    record["status"] = "completed" if completed.returncode == 0 else "failed"
    record["return_code"] = completed.returncode

    source_results = tau2_root / "data" / "simulations" / args.save_to / "results.json"
    if completed.returncode == 0 and source_results.is_file():
        source_payload = json.loads(source_results.read_text(encoding="utf-8"))
        actual_simulation_count, unscored_simulations = assess_result_completeness(
            source_payload,
            expected_simulation_count=expected_simulation_count,
            expected_agent_implementation=args.agent_implementation,
            expected_agent_model=args.agent_model,
            expected_user_implementation="user_simulator",
            expected_user_model=args.user_model,
            expected_domain="retail",
        )
        record["actual_simulation_count"] = actual_simulation_count
        record["unscored_simulations"] = unscored_simulations
        if actual_simulation_count == expected_simulation_count and not unscored_simulations:
            source_num_trials = normalize_result_trial_metadata(
                source_payload,
                expected_num_trials=args.num_trials,
            )
            copied_results = artifact_dir / f"llm_baseline_results_{artifact_label}.json"
            copied_results.write_text(
                json.dumps(source_payload, ensure_ascii=True, indent=2),
                encoding="utf-8",
            )
            record["copied_results"] = str(copied_results)
            record["source_num_trials"] = source_num_trials
            record["artifact_num_trials"] = args.num_trials
            record["trial_metadata_normalized"] = source_num_trials != args.num_trials
        else:
            record["status"] = "incomplete_results"
            record["source_results"] = str(source_results)
            completed = subprocess.CompletedProcess(command, 3)

    launch_record.write_text(
        json.dumps(record, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())

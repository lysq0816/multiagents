"""Prepare or execute the real τ-bench single-LLM Retail baseline."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from after_sales_agents.benchmark.tau2_adapter import load_manifest, locate_tau2_root
from after_sales_agents.benchmark.tau2_runtime import (
    AGENT_INSTRUCTION_PROFILES,
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
    task_ids: list[str],
    enforce_communication_protocol: bool,
) -> list[str]:
    """Build a deterministic official CLI command for the fixed subset."""

    command = [
        str(_tau2_python(tau2_root)),
        str(PROJECT_ROOT / "scripts" / "tau2_with_model_overrides.py"),
        "run",
        "--domain",
        "retail",
        "--agent",
        "llm_agent",
        "--agent-llm",
        agent_model,
        "--agent-llm-args",
        '{"temperature": 0.0}',
        "--user",
        "user_simulator",
        "--user-llm",
        user_model,
        "--user-llm-args",
        '{"temperature": 0.0}',
        "--task-split-name",
        "base",
        "--task-ids",
        *task_ids,
        "--num-trials",
        str(num_trials),
        "--max-concurrency",
        "1",
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
    if enforce_communication_protocol:
        command.append("--enforce-communication-protocol")
    return command


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
    parser.add_argument("--task-ids", nargs="+")
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
    args = parser.parse_args()

    manifest_task_ids = [task.task_id for task in load_manifest().tasks]
    task_ids = args.task_ids or manifest_task_ids
    unknown_task_ids = sorted(set(task_ids) - set(manifest_task_ids))
    if unknown_task_ids:
        parser.error(f"Task IDs are outside the fixed manifest: {unknown_task_ids}")

    protocol = "strict" if args.enforce_communication_protocol else "compatible"
    artifact_label = args.artifact_label or protocol
    if not artifact_label.replace("-", "").replace("_", "").isalnum():
        parser.error("--artifact-label may contain only letters, numbers, '-' and '_'")

    tau2_root = locate_tau2_root(args.tau2_root)
    command = build_command(
        tau2_root,
        agent_model=args.agent_model,
        user_model=args.user_model,
        save_to=args.save_to,
        num_trials=args.num_trials,
        task_ids=task_ids,
        enforce_communication_protocol=args.enforce_communication_protocol,
    )
    configured_keys = load_model_credentials()
    record = {
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": "execute" if args.execute else "dry_run",
        "tau2_root": str(tau2_root),
        "task_ids": task_ids,
        "agent_model": args.agent_model,
        "user_model": args.user_model,
        "evaluator_model": args.evaluator_model,
        "agent_instruction_profile": args.agent_instruction_profile,
        "official_agent_prompt": (
            args.agent_instruction_profile == OFFICIAL_AGENT_INSTRUCTION_PROFILE
        ),
        "num_trials": args.num_trials,
        "enforce_communication_protocol": args.enforce_communication_protocol,
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
    )
    completed = subprocess.run(command, cwd=tau2_root, env=environment, check=False)
    record["status"] = "completed" if completed.returncode == 0 else "failed"
    record["return_code"] = completed.returncode

    source_results = tau2_root / "data" / "simulations" / args.save_to / "results.json"
    if completed.returncode == 0 and source_results.is_file():
        copied_results = artifact_dir / f"llm_baseline_results_{artifact_label}.json"
        shutil.copy2(source_results, copied_results)
        record["copied_results"] = str(copied_results)

    launch_record.write_text(
        json.dumps(record, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())

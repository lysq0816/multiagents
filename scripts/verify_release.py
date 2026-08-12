"""Run deterministic release checks without external network or model calls."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from after_sales_agents.api import app
from after_sales_agents.benchmark.experiment_models import ExperimentReport
from after_sales_agents.policy.catalog import load_policy_catalog

REQUIRED_PATHS = {
    "/health",
    "/api/v1/routing/preview",
    "/api/v1/policy/search",
    "/api/v1/policy/eligibility",
    "/api/v1/collaboration/review",
    "/api/v1/planning/review",
    "/api/v1/review/audit",
    "/api/v1/review/decision",
    "/api/v1/review/verify-state",
}


def _run(command: list[str]) -> dict[str, object]:
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return {
        "command": command,
        "return_code": completed.returncode,
        "passed": completed.returncode == 0,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "artifacts" / "day10" / "release_verification.json",
    )
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args()

    paths = set(app.openapi()["paths"])
    experiment_report_path = PROJECT_ROOT / "artifacts" / "day8" / "experiment_report.json"
    experiment_report = (
        ExperimentReport.model_validate_json(experiment_report_path.read_text(encoding="utf-8"))
        if experiment_report_path.is_file()
        else None
    )
    ui_index = PROJECT_ROOT / "src" / "after_sales_agents" / "ui" / "index.html"
    demo_scripts = [
        PROJECT_ROOT / "scripts" / "run_day4_collaboration_demo.py",
        PROJECT_ROOT / "scripts" / "run_day5_planning_demo.py",
        PROJECT_ROOT / "scripts" / "run_day6_review_demo.py",
        PROJECT_ROOT / "scripts" / "run_day8_experiment.py",
        PROJECT_ROOT / "scripts" / "run_day9_reliability_demo.py",
        PROJECT_ROOT / "scripts" / "run_delivery_scenarios.py",
    ]
    static_checks = {
        "api_version": app.version,
        "required_api_paths_present": REQUIRED_PATHS.issubset(paths),
        "missing_api_paths": sorted(REQUIRED_PATHS - paths),
        "policy_clause_count": len(load_policy_catalog().clauses),
        "dockerfile_present": (PROJECT_ROOT / "Dockerfile").is_file(),
        "compose_present": (PROJECT_ROOT / "compose.yaml").is_file(),
        "readme_present": (PROJECT_ROOT / "README.md").is_file(),
        "development_log_present": (PROJECT_ROOT / "docs" / "DEVLOG.md").is_file(),
        "operator_ui_present": ui_index.is_file(),
        "deterministic_demo_script_count": sum(path.is_file() for path in demo_scripts),
        "day8_experiment_report_present": experiment_report is not None,
        "day8_task_count": experiment_report.task_count if experiment_report else 0,
        "day8_architecture_count": experiment_report.architecture_count if experiment_report else 0,
        "day8_repetitions_per_task": (
            experiment_report.repetitions_per_task if experiment_report else 0
        ),
        "day8_total_run_count": experiment_report.total_run_count if experiment_report else 0,
        "day8_real_write_operations": (
            experiment_report.real_write_operations if experiment_report else None
        ),
        "docker_runtime_validated": False,
        "docker_runtime_note": (
            "Docker CLI is optional for offline release checks; run "
            "`docker compose config` on a Docker-enabled host."
        ),
    }
    commands = []
    if not args.skip_tests:
        commands = [
            _run(["uv", "run", "pytest", "-q", "-p", "no:cacheprovider"]),
            _run(["uv", "run", "ruff", "check", "."]),
            _run(["uv", "run", "ruff", "format", "--check", "."]),
        ]
    passed = (
        static_checks["required_api_paths_present"]
        and static_checks["policy_clause_count"] == 14
        and static_checks["dockerfile_present"]
        and static_checks["compose_present"]
        and static_checks["readme_present"]
        and static_checks["development_log_present"]
        and static_checks["operator_ui_present"]
        and static_checks["deterministic_demo_script_count"] == 6
        and static_checks["day8_task_count"] == 30
        and static_checks["day8_architecture_count"] == 4
        and static_checks["day8_repetitions_per_task"] >= 3
        and static_checks["day8_total_run_count"] >= 360
        and static_checks["day8_real_write_operations"] == 0
        and all(check["passed"] for check in commands)
    )
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "passed": passed,
        "offline": True,
        "model_calls": 0,
        "write_tool_calls": 0,
        "static_checks": static_checks,
        "commands": commands,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "passed": passed,
                "api_version": app.version,
                "required_api_paths_present": static_checks["required_api_paths_present"],
                "policy_clause_count": static_checks["policy_clause_count"],
                "checks_run": len(commands),
                "output": str(args.output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

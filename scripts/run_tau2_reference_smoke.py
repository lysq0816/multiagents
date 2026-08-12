"""Run official Retail tools with reference actions as an integration smoke test."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from after_sales_agents.benchmark.reference_smoke import run_reference_smoke
from after_sales_agents.benchmark.tau2_adapter import locate_tau2_root


def _external_python(tau2_root: Path) -> Path:
    candidates = (
        tau2_root / ".venv" / "Scripts" / "python.exe",
        tau2_root / ".venv" / "bin" / "python",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "τ-bench virtual environment not found; run `uv sync --no-dev` in its root"
    )


def _rerun_in_tau2_environment(tau2_root: Path, output_dir: Path) -> int:
    environment = os.environ.copy()
    existing_pythonpath = environment.get("PYTHONPATH")
    source_path = str(PROJECT_ROOT / "src")
    environment["PYTHONPATH"] = (
        source_path + os.pathsep + existing_pythonpath if existing_pythonpath else source_path
    )
    environment["PYTHONUTF8"] = "1"
    command = [
        str(_external_python(tau2_root)),
        str(Path(__file__).resolve()),
        "--tau2-root",
        str(tau2_root),
        "--output-dir",
        str(output_dir),
    ]
    return subprocess.run(command, cwd=PROJECT_ROOT, env=environment, check=False).returncode


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tau2-root", type=Path)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "artifacts" / "day2",
    )
    args = parser.parse_args()
    tau2_root = locate_tau2_root(args.tau2_root)
    if importlib.util.find_spec("tau2") is None:
        return _rerun_in_tau2_environment(tau2_root, args.output_dir)

    report = run_reference_smoke(args.output_dir, tau2_root=tau2_root)
    summary = {
        "benchmark": report["benchmark"],
        "benchmark_version": report["benchmark_version"],
        "mode": report["mode"],
        "passed": f"{report['passed_task_count']}/{report['task_count']}",
        "environment_pass_rate": report["environment_pass_rate"],
        "total_tool_calls": report["total_tool_calls"],
        "mean_latency_seconds": report["mean_latency_seconds"],
        "comparable_to_llm_baseline": report["comparable_to_llm_baseline"],
        "report_path": str(args.output_dir / "reference_smoke_report.json"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if report["passed_task_count"] == report["task_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

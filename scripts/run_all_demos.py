"""Run every deterministic project demo and summarize its artifacts."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DETERMINISTIC_DEMOS = [
    ("day4_specialist_handoff", "scripts/run_day4_collaboration_demo.py"),
    ("day5_planning", "scripts/run_day5_planning_demo.py"),
    ("day6_review", "scripts/run_day6_review_demo.py"),
    ("day8_experiment_matrix", "scripts/run_day8_experiment.py"),
    ("day9_reliability", "scripts/run_day9_reliability_demo.py"),
    ("day10_delivery_scenarios", "scripts/run_delivery_scenarios.py"),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "artifacts" / "day10" / "all_demos.json",
    )
    args = parser.parse_args()

    results = []
    for name, script in DETERMINISTIC_DEMOS:
        completed = subprocess.run(
            [sys.executable, script],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
            check=False,
        )
        results.append(
            {
                "name": name,
                "script": script,
                "passed": completed.returncode == 0,
                "return_code": completed.returncode,
                "stdout": completed.stdout.strip(),
                "stderr": completed.stderr.strip(),
            }
        )

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "offline": True,
        "model_calls": 0,
        "write_tool_calls": 0,
        "demo_count": len(results),
        "passed_demo_count": sum(1 for result in results if result["passed"]),
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "passed": f"{report['passed_demo_count']}/{report['demo_count']}",
                "model_calls": 0,
                "write_tool_calls": 0,
                "output": str(args.output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if report["passed_demo_count"] == report["demo_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

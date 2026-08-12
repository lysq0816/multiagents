"""Generate an optional non-official business diagnostic for one task."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from after_sales_agents.benchmark.business_evaluator import (
    evaluate_business_compatibility,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("result", type=Path, help="Official τ2 results.json or copied artifact")
    parser.add_argument("--task-id", default="38")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    result_path = args.result.resolve()
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    task = next(
        (task for task in payload.get("tasks", []) if str(task.get("id")) == args.task_id),
        None,
    )
    simulation = next(
        (
            simulation
            for simulation in payload.get("simulations", [])
            if str(simulation.get("task_id")) == args.task_id
        ),
        None,
    )
    if task is None or simulation is None:
        parser.error(f"task {args.task_id} is not present in {result_path}")

    report = evaluate_business_compatibility(task, simulation)
    report["generated_at"] = datetime.now(UTC).isoformat()
    report["source_result"] = str(result_path)

    output_path = args.output or (
        PROJECT_ROOT / "artifacts" / "day2" / f"business_evaluation_task_{args.task_id}.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

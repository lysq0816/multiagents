"""Run and persist the offline deterministic Day 8 experiment matrix."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from after_sales_agents.benchmark.experiment_matrix import (
    load_experiment_manifest,
    render_markdown,
    run_experiment,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/day8"))
    args = parser.parse_args()

    report = run_experiment(load_experiment_manifest(), repetitions=args.repetitions)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "experiment_report.json"
    markdown_path = args.output_dir / "experiment_report.md"
    json_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "task_count": report.task_count,
                "repetitions_per_task": report.repetitions_per_task,
                "architecture_count": report.architecture_count,
                "total_run_count": report.total_run_count,
                "model_calls": 0,
                "real_write_operations": report.real_write_operations,
                "json_report": str(json_path),
                "markdown_report": str(markdown_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

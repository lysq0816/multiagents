"""Validate the fixed Retail task subset against an official τ-bench checkout."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from after_sales_agents.benchmark.tau2_adapter import validate_official_subset


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tau2-root", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "artifacts" / "day2" / "task_subset_validation.json",
    )
    args = parser.parse_args()

    report = validate_official_subset(tau2_root=args.tau2_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rendered = report.model_dump_json(indent=2)
    args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

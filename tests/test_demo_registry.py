import importlib.util
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_all_demos.py"
SPEC = importlib.util.spec_from_file_location("run_all_demos", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
DETERMINISTIC_DEMOS = MODULE.DETERMINISTIC_DEMOS


def test_deterministic_demo_registry_has_stable_core_demos() -> None:
    names = [name for name, _ in DETERMINISTIC_DEMOS]

    assert names == [
        "day4_specialist_handoff",
        "day5_planning",
        "day6_review",
        "day8_experiment_matrix",
        "day9_reliability",
        "day10_delivery_scenarios",
    ]
    assert all((PROJECT_ROOT / script).is_file() for _, script in DETERMINISTIC_DEMOS)

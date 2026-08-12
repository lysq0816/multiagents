import importlib.util
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_delivery_scenarios.py"
SPEC = importlib.util.spec_from_file_location("run_delivery_scenarios", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_five_delivery_scenarios_cover_ready_clarification_and_conflict() -> None:
    results = MODULE.run_scenarios()

    assert len(results) == 5
    for name in ("cancel_ready", "return_ready", "exchange_ready"):
        assert results[name]["planning_status"] == "ready_for_review"
        assert results[name]["audit_status"] == "awaiting_human_decision"
        assert results[name]["can_request_human_decision"] is True
        assert results[name]["can_execute"] is False
    assert results["missing_confirmation"]["planning_status"] == "needs_clarification"
    assert results["missing_confirmation"]["audit_status"] == "rejected_by_auditor"
    assert results["return_exchange_item_conflict"]["planning_status"] == "blocked"
    assert "item" in results["return_exchange_item_conflict"]["issue_types"]

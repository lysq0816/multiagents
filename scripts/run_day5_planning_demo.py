"""Generate readable Day 5 examples without model calls or write tools."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from after_sales_agents.agents.models import (
    CollaborationReviewRequest,
    OrderSpecialistRequest,
)
from after_sales_agents.agents.permissions import ToolPermissionGuard
from after_sales_agents.domain.models import ActionType, AgentRole
from after_sales_agents.planning.models import PlanningWorkflowRequest
from after_sales_agents.planning.workflow import PlanningWorkflow
from after_sales_agents.policy.models import FactField, FactSourceType, SourceFact

ORDER_ID = "#W9348897"


def _fact(
    prefix: str,
    field: FactField,
    value: object,
    source_type: FactSourceType,
) -> SourceFact:
    return SourceFact(
        fact_id=f"fact:{prefix}:{field.value}",
        field=field,
        value=value,
        subject_id=ORDER_ID,
        source_type=source_type,
        source_id=f"source:{prefix}:{field.value}",
    )


def _common_facts(prefix: str) -> list[SourceFact]:
    return [
        _fact(prefix, FactField.USER_AUTHENTICATED, True, FactSourceType.TOOL),
        _fact(prefix, FactField.ACTION_DETAILS_PRESENTED, True, FactSourceType.AGENT),
        _fact(prefix, FactField.USER_CONFIRMED, True, FactSourceType.USER),
    ]


def _cancel_review(case_id: str, status: str = "pending") -> CollaborationReviewRequest:
    prefix = f"{case_id}:cancel"
    return CollaborationReviewRequest(
        analysis=OrderSpecialistRequest(
            case_id=case_id,
            action_type=ActionType.CANCEL_ORDER,
            order_id=ORDER_ID,
            provided_facts=[
                *_common_facts(prefix),
                _fact(prefix, FactField.ORDER_ID_CONFIRMED, True, FactSourceType.USER),
                _fact(
                    prefix,
                    FactField.CANCEL_REASON,
                    "no longer needed",
                    FactSourceType.USER,
                ),
            ],
        ),
        order_snapshot={"order_id": ORDER_ID, "status": status},
    )


def _return_review(case_id: str) -> CollaborationReviewRequest:
    prefix = f"{case_id}:return"
    return CollaborationReviewRequest(
        analysis=OrderSpecialistRequest(
            case_id=case_id,
            action_type=ActionType.CREATE_RETURN,
            order_id=ORDER_ID,
            provided_facts=[
                *_common_facts(prefix),
                _fact(prefix, FactField.ORDER_ID_CONFIRMED, True, FactSourceType.USER),
                _fact(prefix, FactField.ITEM_IDS, ["item-blue"], FactSourceType.USER),
                _fact(
                    prefix,
                    FactField.PAYMENT_METHOD_ID,
                    "credit_card_1",
                    FactSourceType.TOOL,
                ),
                _fact(prefix, FactField.PAYMENT_METHOD_EXISTS, True, FactSourceType.TOOL),
                _fact(
                    prefix,
                    FactField.PAYMENT_METHOD_TYPE,
                    "credit_card",
                    FactSourceType.TOOL,
                ),
                _fact(
                    prefix,
                    FactField.PAYMENT_METHOD_IS_ORIGINAL,
                    True,
                    FactSourceType.TOOL,
                ),
            ],
        ),
        order_snapshot={"order_id": ORDER_ID, "status": "delivered"},
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "artifacts" / "day5" / "planning_demo.json",
    )
    args = parser.parse_args()

    guard = ToolPermissionGuard()
    workflow = PlanningWorkflow(guard)
    ready = workflow.review(PlanningWorkflowRequest(reviews=[_cancel_review("demo-ready")]))
    blocked = workflow.review(
        PlanningWorkflowRequest(
            reviews=[
                _cancel_review("demo-conflict", status="pending"),
                _return_review("demo-conflict"),
            ]
        )
    )

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "model_calls": 0,
        "write_tool_calls": 0,
        "planner_can_execute": False,
        "tool_permissions": {
            role.value: sorted(tool.value for tool in guard.allowed_tools(role))
            for role in (
                AgentRole.ORDER_SPECIALIST,
                AgentRole.POLICY_SPECIALIST,
                AgentRole.PLANNER,
            )
        },
        "summary": {
            "ready_scenario": {
                "status": ready.plan.status.value,
                "candidate_count": len(ready.plan.candidate_actions),
                "can_advance_to_review": ready.plan.can_advance_to_review,
                "can_execute": ready.plan.can_execute,
            },
            "conflict_scenario": {
                "status": blocked.plan.status.value,
                "conflict_types": [issue.conflict_type.value for issue in blocked.plan.issues],
                "can_advance_to_review": blocked.plan.can_advance_to_review,
                "can_execute": blocked.plan.can_execute,
            },
        },
        "scenarios": {
            "ready_for_review": ready.model_dump(mode="json"),
            "blocked_by_order_conflict": blocked.model_dump(mode="json"),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

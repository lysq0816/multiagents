"""Demonstrate Day 6 audit, approval, and state verification without writes."""

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
from after_sales_agents.review.approval import HumanApprovalGate
from after_sales_agents.review.auditor import IndependentAuditor
from after_sales_agents.review.models import (
    AuditReviewRequest,
    HumanDecisionRequest,
    HumanDecisionType,
    StateVerificationRequest,
)
from after_sales_agents.review.verification import PostExecutionVerifier

CASE_ID = "demo-review-1"
ORDER_ID = "#W9348897"


def _fact(
    field: FactField,
    value: object,
    source_type: FactSourceType,
) -> SourceFact:
    return SourceFact(
        fact_id=f"fact:{CASE_ID}:{field.value}",
        field=field,
        value=value,
        subject_id=ORDER_ID,
        source_type=source_type,
        source_id=f"source:{CASE_ID}:{field.value}",
    )


def _request() -> PlanningWorkflowRequest:
    return PlanningWorkflowRequest(
        reviews=[
            CollaborationReviewRequest(
                analysis=OrderSpecialistRequest(
                    case_id=CASE_ID,
                    action_type=ActionType.CANCEL_ORDER,
                    order_id=ORDER_ID,
                    provided_facts=[
                        _fact(
                            FactField.USER_AUTHENTICATED,
                            True,
                            FactSourceType.TOOL,
                        ),
                        _fact(
                            FactField.ACTION_DETAILS_PRESENTED,
                            True,
                            FactSourceType.AGENT,
                        ),
                        _fact(FactField.USER_CONFIRMED, True, FactSourceType.USER),
                        _fact(
                            FactField.ORDER_ID_CONFIRMED,
                            True,
                            FactSourceType.USER,
                        ),
                        _fact(
                            FactField.CANCEL_REASON,
                            "no longer needed",
                            FactSourceType.USER,
                        ),
                    ],
                ),
                order_snapshot={"order_id": ORDER_ID, "status": "pending"},
            )
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "artifacts" / "day6" / "review_demo.json",
    )
    args = parser.parse_args()

    planning = PlanningWorkflow().review(_request())
    audit = IndependentAuditor().review(AuditReviewRequest(planning=planning))
    approval = HumanApprovalGate().decide(
        HumanDecisionRequest(
            planning=planning,
            review=audit,
            decision=HumanDecisionType.APPROVE,
            decided_by="demo-operator",
            reason="Demo approval after checking facts, policy, entities, and arguments.",
        )
    )
    authorization = approval.authorization
    if authorization is None:
        raise RuntimeError("the demo approval did not create an authorization")

    simulated_after_snapshot = {
        "order_id": ORDER_ID,
        "status": "cancelled",
        "cancel_reason": "no longer needed",
    }
    verification = PostExecutionVerifier().verify(
        StateVerificationRequest(
            authorization=authorization,
            before_snapshots={ORDER_ID: {"order_id": ORDER_ID, "status": "pending"}},
            after_snapshots={ORDER_ID: simulated_after_snapshot},
        )
    )

    guard = ToolPermissionGuard()
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "model_calls": 0,
        "write_tool_calls": 0,
        "after_snapshot_is_simulated": True,
        "tool_permissions": {
            role.value: sorted(tool.value for tool in guard.allowed_tools(role))
            for role in (AgentRole.PLANNER, AgentRole.AUDITOR)
        },
        "summary": {
            "planning_status": planning.plan.status.value,
            "audit_status": audit.status.value,
            "audit_checks": {check.check_type.value: check.status.value for check in audit.checks},
            "human_decision": approval.decision.value,
            "execution_authorized": approval.execution_authorized,
            "can_execute_now": approval.can_execute_now,
            "write_executed": approval.write_executed,
            "simulated_state_verification": verification.status.value,
        },
        "planning": planning.model_dump(mode="json"),
        "audit": audit.model_dump(mode="json"),
        "approval": approval.model_dump(mode="json"),
        "simulated_after_snapshot": simulated_after_snapshot,
        "verification": verification.model_dump(mode="json"),
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

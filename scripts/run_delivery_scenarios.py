"""Run five stable end-to-end business scenarios without model or write calls."""

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
    ExchangeTargetRequest,
    OrderSpecialistRequest,
)
from after_sales_agents.domain.models import ActionType
from after_sales_agents.planning.models import PlanningWorkflowRequest
from after_sales_agents.planning.workflow import PlanningWorkflow
from after_sales_agents.policy.models import FactField, FactSourceType, SourceFact
from after_sales_agents.review.auditor import IndependentAuditor
from after_sales_agents.review.models import AuditReviewRequest


def _fact(
    case_id: str,
    order_id: str,
    field: FactField,
    value: object,
    source_type: FactSourceType,
    *,
    scope: str,
) -> SourceFact:
    return SourceFact(
        fact_id=f"fact:{case_id}:{scope}:{field.value}",
        field=field,
        value=value,
        subject_id=order_id,
        source_type=source_type,
        source_id=f"source:{case_id}:{scope}:{field.value}",
    )


def _common(
    case_id: str,
    order_id: str,
    *,
    scope: str,
    confirmed: bool = True,
) -> list[SourceFact]:
    facts = [
        _fact(
            case_id,
            order_id,
            FactField.USER_AUTHENTICATED,
            True,
            FactSourceType.TOOL,
            scope=scope,
        ),
        _fact(
            case_id,
            order_id,
            FactField.ACTION_DETAILS_PRESENTED,
            True,
            FactSourceType.AGENT,
            scope=scope,
        ),
    ]
    if confirmed:
        facts.append(
            _fact(
                case_id,
                order_id,
                FactField.USER_CONFIRMED,
                True,
                FactSourceType.USER,
                scope=scope,
            )
        )
    return facts


def _cancel(
    case_id: str,
    order_id: str,
    *,
    confirmed: bool = True,
) -> CollaborationReviewRequest:
    scope = "cancel"
    return CollaborationReviewRequest(
        analysis=OrderSpecialistRequest(
            case_id=case_id,
            action_type=ActionType.CANCEL_ORDER,
            order_id=order_id,
            provided_facts=[
                *_common(case_id, order_id, scope=scope, confirmed=confirmed),
                _fact(
                    case_id,
                    order_id,
                    FactField.ORDER_ID_CONFIRMED,
                    True,
                    FactSourceType.USER,
                    scope=scope,
                ),
                _fact(
                    case_id,
                    order_id,
                    FactField.CANCEL_REASON,
                    "no longer needed",
                    FactSourceType.USER,
                    scope=scope,
                ),
            ],
        ),
        order_snapshot={"order_id": order_id, "status": "pending"},
    )


def _return(
    case_id: str,
    order_id: str,
    *,
    item_id: str = "item-red",
) -> CollaborationReviewRequest:
    scope = "return"
    return CollaborationReviewRequest(
        analysis=OrderSpecialistRequest(
            case_id=case_id,
            action_type=ActionType.CREATE_RETURN,
            order_id=order_id,
            provided_facts=[
                *_common(case_id, order_id, scope=scope),
                _fact(
                    case_id,
                    order_id,
                    FactField.ORDER_ID_CONFIRMED,
                    True,
                    FactSourceType.USER,
                    scope=scope,
                ),
                _fact(
                    case_id,
                    order_id,
                    FactField.ITEM_IDS,
                    [item_id],
                    FactSourceType.USER,
                    scope=scope,
                ),
                _fact(
                    case_id,
                    order_id,
                    FactField.PAYMENT_METHOD_ID,
                    "credit_card_demo",
                    FactSourceType.TOOL,
                    scope=scope,
                ),
                _fact(
                    case_id,
                    order_id,
                    FactField.PAYMENT_METHOD_TYPE,
                    "credit_card",
                    FactSourceType.TOOL,
                    scope=scope,
                ),
                _fact(
                    case_id,
                    order_id,
                    FactField.PAYMENT_METHOD_EXISTS,
                    True,
                    FactSourceType.TOOL,
                    scope=scope,
                ),
                _fact(
                    case_id,
                    order_id,
                    FactField.PAYMENT_METHOD_IS_ORIGINAL,
                    True,
                    FactSourceType.TOOL,
                    scope=scope,
                ),
            ],
        ),
        order_snapshot={"order_id": order_id, "status": "delivered"},
    )


def _exchange(
    case_id: str,
    order_id: str,
    *,
    item_id: str = "item-red",
) -> CollaborationReviewRequest:
    scope = "exchange"
    return CollaborationReviewRequest(
        analysis=OrderSpecialistRequest(
            case_id=case_id,
            action_type=ActionType.EXCHANGE_ITEMS,
            order_id=order_id,
            provided_facts=[
                *_common(case_id, order_id, scope=scope),
                _fact(
                    case_id,
                    order_id,
                    FactField.PAYMENT_METHOD_ID,
                    "credit_card_demo",
                    FactSourceType.TOOL,
                    scope=scope,
                ),
                _fact(
                    case_id,
                    order_id,
                    FactField.PAYMENT_METHOD_TYPE,
                    "credit_card",
                    FactSourceType.TOOL,
                    scope=scope,
                ),
                _fact(
                    case_id,
                    order_id,
                    FactField.PAYMENT_METHOD_EXISTS,
                    True,
                    FactSourceType.TOOL,
                    scope=scope,
                ),
            ],
            exchange_targets=[
                ExchangeTargetRequest(
                    product_id="product-demo",
                    current_item_id=item_id,
                    target_item_id="item-blue",
                    source_id=f"user-message:{case_id}:exchange-target",
                )
            ],
        ),
        order_snapshot={"order_id": order_id, "status": "delivered"},
        product_snapshots={
            "product-demo": {
                "product_id": "product-demo",
                "variants": {
                    item_id: {"available": True, "options": {"color": "red"}},
                    "item-blue": {
                        "available": True,
                        "options": {"color": "blue"},
                    },
                },
            }
        },
    )


def scenario_requests() -> dict[str, PlanningWorkflowRequest]:
    return {
        "cancel_ready": PlanningWorkflowRequest(
            reviews=[_cancel("demo-cancel-ready", "#DEMO-CANCEL")]
        ),
        "return_ready": PlanningWorkflowRequest(
            reviews=[_return("demo-return-ready", "#DEMO-RETURN")]
        ),
        "exchange_ready": PlanningWorkflowRequest(
            reviews=[_exchange("demo-exchange-ready", "#DEMO-EXCHANGE")]
        ),
        "missing_confirmation": PlanningWorkflowRequest(
            reviews=[
                _cancel(
                    "demo-missing-confirmation",
                    "#DEMO-MISSING",
                    confirmed=False,
                )
            ]
        ),
        "return_exchange_item_conflict": PlanningWorkflowRequest(
            reviews=[
                _return("demo-item-conflict", "#DEMO-CONFLICT"),
                _exchange("demo-item-conflict", "#DEMO-CONFLICT"),
            ]
        ),
    }


def run_scenarios() -> dict[str, object]:
    workflow = PlanningWorkflow()
    auditor = IndependentAuditor()
    results = {}
    for name, request in scenario_requests().items():
        planning = workflow.review(request)
        audit = auditor.review(AuditReviewRequest(planning=planning))
        results[name] = {
            "planning_status": planning.plan.status.value,
            "candidate_count": len(planning.plan.candidate_actions),
            "issue_types": [issue.conflict_type.value for issue in planning.plan.issues],
            "clarification_questions": planning.plan.clarification_questions,
            "audit_status": audit.status.value,
            "can_request_human_decision": audit.can_request_human_decision,
            "can_execute": audit.can_execute,
        }
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "artifacts" / "day10" / "delivery_scenarios.json",
    )
    args = parser.parse_args()
    results = run_scenarios()
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "offline": True,
        "model_calls": 0,
        "write_tool_calls": 0,
        "scenario_count": len(results),
        "scenarios": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

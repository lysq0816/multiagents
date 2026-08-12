import pytest

from after_sales_agents.agents.models import (
    CollaborationReviewRequest,
    ExchangeTargetRequest,
    OrderSpecialistRequest,
)
from after_sales_agents.agents.permissions import (
    ToolName,
    ToolPermissionDenied,
    ToolPermissionGuard,
)
from after_sales_agents.agents.workflow import SpecialistWorkflow
from after_sales_agents.api import app
from after_sales_agents.domain.models import ActionType, AgentRole
from after_sales_agents.planning.models import (
    ConflictType,
    PlannerRequest,
    PlanningWorkflowRequest,
    PlanStatus,
)
from after_sales_agents.planning.planner import CandidateActionPlanner
from after_sales_agents.planning.workflow import PlanningWorkflow
from after_sales_agents.policy.models import FactField, FactSourceType, SourceFact


def _fact(
    case_id: str,
    field: FactField,
    value: object,
    source_type: FactSourceType = FactSourceType.TOOL,
) -> SourceFact:
    return SourceFact(
        fact_id=f"fact:{case_id}:{field.value}",
        field=field,
        value=value,
        subject_id="#ORDER-1",
        source_type=source_type,
        source_id=f"source:{case_id}:{field.value}",
    )


def _common(case_id: str, *, confirmed: bool = True) -> list[SourceFact]:
    facts = [
        _fact(case_id, FactField.USER_AUTHENTICATED, True),
        _fact(
            case_id,
            FactField.ACTION_DETAILS_PRESENTED,
            True,
            FactSourceType.AGENT,
        ),
    ]
    if confirmed:
        facts.append(_fact(case_id, FactField.USER_CONFIRMED, True, FactSourceType.USER))
    return facts


def _cancel_review(
    case_id: str = "case-plan",
    *,
    status: str = "pending",
    confirmed: bool = True,
) -> CollaborationReviewRequest:
    return CollaborationReviewRequest(
        analysis=OrderSpecialistRequest(
            case_id=case_id,
            action_type=ActionType.CANCEL_ORDER,
            order_id="#ORDER-1",
            provided_facts=[
                *_common(case_id, confirmed=confirmed),
                _fact(
                    case_id,
                    FactField.ORDER_ID_CONFIRMED,
                    True,
                    FactSourceType.USER,
                ),
                _fact(
                    case_id,
                    FactField.CANCEL_REASON,
                    "no longer needed",
                    FactSourceType.USER,
                ),
            ],
        ),
        order_snapshot={"order_id": "#ORDER-1", "status": status},
    )


def _return_review(
    case_id: str = "case-plan",
    *,
    item_id: str = "item-red",
) -> CollaborationReviewRequest:
    return CollaborationReviewRequest(
        analysis=OrderSpecialistRequest(
            case_id=case_id,
            action_type=ActionType.CREATE_RETURN,
            order_id="#ORDER-1",
            provided_facts=[
                *_common(case_id),
                _fact(
                    case_id,
                    FactField.ORDER_ID_CONFIRMED,
                    True,
                    FactSourceType.USER,
                ),
                _fact(case_id, FactField.ITEM_IDS, [item_id], FactSourceType.USER),
                _fact(case_id, FactField.PAYMENT_METHOD_ID, "credit_card_1"),
                _fact(case_id, FactField.PAYMENT_METHOD_EXISTS, True),
                _fact(case_id, FactField.PAYMENT_METHOD_TYPE, "credit_card"),
                _fact(case_id, FactField.PAYMENT_METHOD_IS_ORIGINAL, True),
            ],
        ),
        order_snapshot={"order_id": "#ORDER-1", "status": "delivered"},
    )


def _exchange_review(
    case_id: str = "case-plan",
    *,
    price_difference: str = "10.00",
) -> CollaborationReviewRequest:
    return CollaborationReviewRequest(
        analysis=OrderSpecialistRequest(
            case_id=case_id,
            action_type=ActionType.EXCHANGE_ITEMS,
            order_id="#ORDER-1",
            provided_facts=[
                *_common(case_id),
                _fact(case_id, FactField.PAYMENT_METHOD_ID, "credit_card_1"),
                _fact(case_id, FactField.PAYMENT_METHOD_TYPE, "credit_card"),
                _fact(case_id, FactField.PAYMENT_METHOD_EXISTS, True),
                _fact(case_id, FactField.PRICE_DIFFERENCE, price_difference),
            ],
            exchange_targets=[
                ExchangeTargetRequest(
                    product_id="product-1",
                    current_item_id="item-red",
                    target_item_id="item-blue",
                    source_id=f"user-message:{case_id}:target",
                )
            ],
        ),
        order_snapshot={"order_id": "#ORDER-1", "status": "delivered"},
        product_snapshots={
            "product-1": {
                "product_id": "product-1",
                "variants": {
                    "item-red": {"available": True, "options": {"color": "red"}},
                    "item-blue": {"available": True, "options": {"color": "blue"}},
                },
            }
        },
    )


def test_eligible_cancel_becomes_a_grounded_review_candidate() -> None:
    result = PlanningWorkflow().review(PlanningWorkflowRequest(reviews=[_cancel_review()]))

    assert result.plan.status is PlanStatus.READY_FOR_REVIEW
    assert result.plan.can_advance_to_review is True
    assert result.plan.can_execute is False
    assert len(result.plan.candidate_actions) == 1
    candidate = result.plan.candidate_actions[0]
    assert candidate.action_type is ActionType.CANCEL_ORDER
    assert candidate.arguments["reason"] == "no longer needed"
    assert candidate.requires_approval is True
    assert candidate.can_execute is False
    assert candidate.fact_ids
    assert candidate.policy_clause_ids


def test_missing_confirmation_returns_a_specific_clarification() -> None:
    result = PlanningWorkflow().review(
        PlanningWorkflowRequest(reviews=[_cancel_review(confirmed=False)])
    )

    assert result.plan.status is PlanStatus.NEEDS_CLARIFICATION
    assert result.plan.candidate_actions == []
    assert result.plan.can_advance_to_review is False
    assert any(
        issue.conflict_type is ConflictType.MISSING_INFORMATION for issue in result.plan.issues
    )
    assert any("user.confirmed" in question for question in result.plan.clarification_questions)


def test_policy_ineligible_action_is_blocked_without_a_candidate() -> None:
    result = PlanningWorkflow().review(
        PlanningWorkflowRequest(reviews=[_cancel_review(status="delivered")])
    )

    assert result.plan.status is PlanStatus.BLOCKED
    assert result.plan.candidate_actions == []
    assert any(issue.conflict_type is ConflictType.POLICY for issue in result.plan.issues)


def test_cancel_and_return_on_conflicting_order_snapshots_are_blocked() -> None:
    result = PlanningWorkflow().review(
        PlanningWorkflowRequest(
            reviews=[_cancel_review(), _return_review()],
        )
    )

    assert result.plan.status is PlanStatus.BLOCKED
    assert {candidate.action_type for candidate in result.plan.candidate_actions} == {
        ActionType.CANCEL_ORDER,
        ActionType.CREATE_RETURN,
    }
    order_issues = [
        issue for issue in result.plan.issues if issue.conflict_type is ConflictType.ORDER
    ]
    assert len(order_issues) == 2
    assert any(FactField.ORDER_STATUS.value in issue.fields for issue in order_issues)


def test_same_item_cannot_be_returned_and_exchanged() -> None:
    result = PlanningWorkflow().review(
        PlanningWorkflowRequest(reviews=[_return_review(), _exchange_review()])
    )

    assert result.plan.status is PlanStatus.BLOCKED
    item_issue = next(
        issue for issue in result.plan.issues if issue.conflict_type is ConflictType.ITEM
    )
    assert "item-red" in item_issue.description
    exchange = next(
        candidate
        for candidate in result.plan.candidate_actions
        if candidate.action_type is ActionType.EXCHANGE_ITEMS
    )
    assert exchange.target_item_ids == ["item-blue"]


def test_conflicting_exchange_amounts_require_clarification() -> None:
    result = PlanningWorkflow().review(
        PlanningWorkflowRequest(
            reviews=[
                _exchange_review(price_difference="10.00"),
                _exchange_review(price_difference="25.00"),
            ]
        )
    )

    assert result.plan.status is PlanStatus.NEEDS_CLARIFICATION
    assert {issue.conflict_type for issue in result.plan.issues} == {
        ConflictType.AMOUNT,
        ConflictType.DUPLICATE_ACTION,
    }
    assert len(result.plan.candidate_actions) == 1
    assert len(result.plan.candidate_actions[0].source_handoff_ids) == 2
    assert any("price difference" in question for question in result.plan.clarification_questions)


def test_disagreeing_policy_conclusions_are_blocked() -> None:
    workflow = SpecialistWorkflow()
    eligible = workflow.review(_cancel_review()).policy_handoff
    ineligible = workflow.review(_cancel_review(status="delivered")).policy_handoff
    ineligible = ineligible.model_copy(update={"handoff_id": f"{ineligible.handoff_id}:ineligible"})

    result = CandidateActionPlanner().plan(
        PlannerRequest(case_id="case-plan", handoffs=[eligible, ineligible])
    )

    assert result.status is PlanStatus.BLOCKED
    assert any(
        issue.conflict_type is ConflictType.POLICY and "disagree" in issue.description
        for issue in result.issues
    )


def test_planner_has_no_read_or_write_tools() -> None:
    guard = ToolPermissionGuard()

    assert guard.allowed_tools(AgentRole.PLANNER) == frozenset()
    with pytest.raises(ToolPermissionDenied):
        guard.ensure_allowed(AgentRole.PLANNER, ToolName.GET_ORDER_DETAILS)
    with pytest.raises(ToolPermissionDenied):
        guard.ensure_allowed(AgentRole.PLANNER, ToolName.CANCEL_PENDING_ORDER)


def test_openapi_exposes_planning_review() -> None:
    assert tuple(map(int, app.version.split("."))) >= (0, 5, 0)
    assert "/api/v1/planning/review" in app.openapi()["paths"]

import pytest
from pydantic import ValidationError

from after_sales_agents.agents.models import (
    CollaborationReviewRequest,
    OrderSpecialistRequest,
)
from after_sales_agents.agents.permissions import (
    ToolName,
    ToolPermissionDenied,
    ToolPermissionGuard,
)
from after_sales_agents.api import app
from after_sales_agents.domain.models import ActionType, AgentRole
from after_sales_agents.planning.models import PlanningWorkflowRequest, PlanStatus
from after_sales_agents.planning.workflow import PlanningWorkflow
from after_sales_agents.policy.models import FactField, FactSourceType, SourceFact
from after_sales_agents.review.approval import ApprovalGateError, HumanApprovalGate
from after_sales_agents.review.auditor import IndependentAuditor, plan_digest
from after_sales_agents.review.models import (
    ActionModification,
    ApprovalStatus,
    AuditReviewRequest,
    HumanDecisionRequest,
    HumanDecisionType,
    ReviewCheckStatus,
    ReviewStatus,
    StateVerificationRequest,
    StateVerificationStatus,
)
from after_sales_agents.review.verification import PostExecutionVerifier


def _fact(
    field: FactField,
    value: object,
    source_type: FactSourceType,
    *,
    case_id: str = "case-review",
) -> SourceFact:
    return SourceFact(
        fact_id=f"fact:{case_id}:{field.value}",
        field=field,
        value=value,
        subject_id="#ORDER-1",
        source_type=source_type,
        source_id=f"source:{case_id}:{field.value}",
    )


def _cancel_review(
    *,
    confirmed: bool = True,
    status: str = "pending",
) -> CollaborationReviewRequest:
    facts = [
        _fact(FactField.USER_AUTHENTICATED, True, FactSourceType.TOOL),
        _fact(FactField.ACTION_DETAILS_PRESENTED, True, FactSourceType.AGENT),
        _fact(FactField.ORDER_ID_CONFIRMED, True, FactSourceType.USER),
        _fact(FactField.CANCEL_REASON, "no longer needed", FactSourceType.USER),
    ]
    if confirmed:
        facts.append(_fact(FactField.USER_CONFIRMED, True, FactSourceType.USER))
    return CollaborationReviewRequest(
        analysis=OrderSpecialistRequest(
            case_id="case-review",
            action_type=ActionType.CANCEL_ORDER,
            order_id="#ORDER-1",
            provided_facts=facts,
        ),
        order_snapshot={"order_id": "#ORDER-1", "status": status},
    )


def _planning(*, confirmed: bool = True, status: str = "pending"):
    return PlanningWorkflow().review(
        PlanningWorkflowRequest(reviews=[_cancel_review(confirmed=confirmed, status=status)])
    )


def _passed_review():
    planning = _planning()
    review = IndependentAuditor().review(AuditReviewRequest(planning=planning))
    return planning, review


def _approve(planning, review):
    return HumanApprovalGate().decide(
        HumanDecisionRequest(
            planning=planning,
            review=review,
            decision=HumanDecisionType.APPROVE,
            decided_by="operator-1",
            reason="Facts, policy, and action arguments were reviewed.",
        )
    )


def test_ready_plan_passes_independent_audit_but_cannot_execute() -> None:
    planning, review = _passed_review()

    assert planning.plan.status is PlanStatus.READY_FOR_REVIEW
    assert review.status is ReviewStatus.AWAITING_HUMAN_DECISION
    assert all(check.status is ReviewCheckStatus.PASSED for check in review.checks)
    assert review.plan_digest == plan_digest(planning)
    assert review.can_request_human_decision is True
    assert review.can_execute is False
    assert review.expected_state_changes[0].expected_status == "cancelled"
    assert review.expected_state_changes[0].expected_fields == {"cancel_reason": "no longer needed"}


def test_non_ready_plan_is_rejected_by_auditor() -> None:
    planning = _planning(confirmed=False)
    review = IndependentAuditor().review(AuditReviewRequest(planning=planning))

    assert review.status is ReviewStatus.REJECTED_BY_AUDITOR
    assert review.can_request_human_decision is False
    assert review.can_execute is False
    assert review.expected_state_changes == []
    assert review.checks[0].status is ReviewCheckStatus.FAILED


def test_tampered_candidate_argument_fails_independent_audit() -> None:
    planning = _planning()
    candidate = planning.plan.candidate_actions[0]
    tampered_candidate = candidate.model_copy(
        update={"arguments": {"reason": "ordered by mistake"}}
    )
    tampered_plan = planning.plan.model_copy(update={"candidate_actions": [tampered_candidate]})
    tampered_planning = planning.model_copy(update={"plan": tampered_plan})

    review = IndependentAuditor().review(AuditReviewRequest(planning=tampered_planning))

    assert review.status is ReviewStatus.REJECTED_BY_AUDITOR
    assert any(
        check.status is ReviewCheckStatus.FAILED and check.check_type.value == "precondition"
        for check in review.checks
    )


def test_tampered_order_handoff_fails_entity_audit() -> None:
    planning = _planning()
    specialist_result = planning.specialist_results[0]
    tampered_order_handoff = specialist_result.order_handoff.model_copy(
        update={
            "payload": specialist_result.order_handoff.payload.model_copy(
                update={"order_id": "#OTHER-ORDER"}
            )
        }
    )
    tampered_specialist = specialist_result.model_copy(
        update={"order_handoff": tampered_order_handoff}
    )
    tampered_planning = planning.model_copy(update={"specialist_results": [tampered_specialist]})

    review = IndependentAuditor().review(AuditReviewRequest(planning=tampered_planning))

    assert review.status is ReviewStatus.REJECTED_BY_AUDITOR
    assert any(
        check.check_type.value == "entity" and check.status is ReviewCheckStatus.FAILED
        for check in review.checks
    )


def test_human_approval_creates_bound_authorization_without_executing() -> None:
    planning, review = _passed_review()

    decision = _approve(planning, review)

    assert decision.status is ApprovalStatus.APPROVED
    assert decision.execution_authorized is True
    assert decision.can_execute_now is False
    assert decision.write_executed is False
    assert decision.authorization is not None
    assert decision.authorization.plan_digest == review.plan_digest
    assert decision.authorization.approved_plan_ids == [planning.plan.candidate_actions[0].plan_id]
    assert decision.authorization.authorizes_execution is True
    assert decision.authorization.write_executed is False


def test_modified_action_loses_authorization_and_requires_re_review() -> None:
    planning, review = _passed_review()
    action = review.reviewed_actions[0]

    decision = HumanApprovalGate().decide(
        HumanDecisionRequest(
            planning=planning,
            review=review,
            decision=HumanDecisionType.MODIFY,
            decided_by="operator-1",
            reason="Use the other policy-allowed cancellation reason.",
            modifications=[
                ActionModification(
                    plan_id=action.plan_id,
                    arguments={"reason": "ordered by mistake"},
                )
            ],
        )
    )

    assert decision.status is ApprovalStatus.MODIFICATION_REQUIRES_REVIEW
    assert decision.authorization is None
    assert decision.requires_re_review is True
    assert decision.execution_authorized is False
    assert decision.can_execute_now is False
    assert decision.revised_actions[0].arguments["reason"] == "ordered by mistake"


def test_human_rejection_never_creates_authorization() -> None:
    planning, review = _passed_review()

    decision = HumanApprovalGate().decide(
        HumanDecisionRequest(
            planning=planning,
            review=review,
            decision=HumanDecisionType.REJECT,
            decided_by="operator-1",
            reason="Customer withdrew the request.",
        )
    )

    assert decision.status is ApprovalStatus.REJECTED
    assert decision.authorization is None
    assert decision.execution_authorized is False
    assert decision.can_execute_now is False


def test_human_decision_rejects_stale_or_tampered_review() -> None:
    planning, review = _passed_review()
    tampered_review = review.model_copy(update={"plan_digest": "0" * 64})

    with pytest.raises(ApprovalGateError, match="stale, modified"):
        _approve(planning, tampered_review)


def test_auditor_rejected_plan_cannot_receive_human_approval() -> None:
    planning = _planning(status="delivered")
    review = IndependentAuditor().review(AuditReviewRequest(planning=planning))

    with pytest.raises(ApprovalGateError):
        _approve(planning, review)


def test_modify_requires_a_real_modification() -> None:
    planning, review = _passed_review()

    with pytest.raises(ValidationError, match="at least one modification"):
        HumanDecisionRequest(
            planning=planning,
            review=review,
            decision=HumanDecisionType.MODIFY,
            decided_by="operator-1",
            reason="Modify it.",
        )


def test_post_execution_state_match_is_verified() -> None:
    planning, review = _passed_review()
    authorization = _approve(planning, review).authorization
    assert authorization is not None

    result = PostExecutionVerifier().verify(
        StateVerificationRequest(
            authorization=authorization,
            before_snapshots={"#ORDER-1": {"order_id": "#ORDER-1", "status": "pending"}},
            after_snapshots={
                "#ORDER-1": {
                    "order_id": "#ORDER-1",
                    "status": "cancelled",
                    "cancel_reason": "no longer needed",
                }
            },
        )
    )

    assert result.status is StateVerificationStatus.MATCHED
    assert result.differences == []


def test_unchanged_snapshot_is_reported_as_not_executed() -> None:
    planning, review = _passed_review()
    authorization = _approve(planning, review).authorization
    assert authorization is not None
    snapshot = {"order_id": "#ORDER-1", "status": "pending"}

    result = PostExecutionVerifier().verify(
        StateVerificationRequest(
            authorization=authorization,
            before_snapshots={"#ORDER-1": snapshot},
            after_snapshots={"#ORDER-1": snapshot},
        )
    )

    assert result.status is StateVerificationStatus.NOT_EXECUTED
    assert any(difference.path.endswith("snapshot_change") for difference in result.differences)


def test_changed_but_wrong_state_is_reported_as_mismatch() -> None:
    planning, review = _passed_review()
    authorization = _approve(planning, review).authorization
    assert authorization is not None

    result = PostExecutionVerifier().verify(
        StateVerificationRequest(
            authorization=authorization,
            before_snapshots={"#ORDER-1": {"order_id": "#ORDER-1", "status": "pending"}},
            after_snapshots={"#ORDER-1": {"order_id": "#ORDER-1", "status": "processed"}},
        )
    )

    assert result.status is StateVerificationStatus.MISMATCH
    assert any(difference.path.endswith("status") for difference in result.differences)


def test_auditor_has_no_read_or_write_tools() -> None:
    guard = ToolPermissionGuard()

    assert guard.allowed_tools(AgentRole.AUDITOR) == frozenset()
    with pytest.raises(ToolPermissionDenied):
        guard.ensure_allowed(AgentRole.AUDITOR, ToolName.GET_ORDER_DETAILS)
    with pytest.raises(ToolPermissionDenied):
        guard.ensure_allowed(AgentRole.AUDITOR, ToolName.CANCEL_PENDING_ORDER)


def test_openapi_exposes_review_endpoints() -> None:
    paths = app.openapi()["paths"]

    assert tuple(map(int, app.version.split("."))) >= (0, 5, 0)
    assert "/api/v1/review/audit" in paths
    assert "/api/v1/review/decision" in paths
    assert "/api/v1/review/verify-state" in paths

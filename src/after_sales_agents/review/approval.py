"""Human approval decisions bound to the exact audited plan digest."""

from __future__ import annotations

from copy import deepcopy

from after_sales_agents.review.auditor import IndependentAuditor
from after_sales_agents.review.models import (
    ApprovalStatus,
    AuditReviewRequest,
    ExecutionAuthorization,
    HumanDecisionRequest,
    HumanDecisionResult,
    HumanDecisionType,
    ReviewStatus,
)


class ApprovalGateError(ValueError):
    pass


class HumanApprovalGate:
    def decide(self, request: HumanDecisionRequest) -> HumanDecisionResult:
        review = request.review
        expected_review = IndependentAuditor().review(AuditReviewRequest(planning=request.planning))
        if review.model_dump(mode="json", exclude={"reviewed_at"}) != expected_review.model_dump(
            mode="json", exclude={"reviewed_at"}
        ):
            raise ApprovalGateError(
                "review is stale, modified, or does not match the planning result"
            )
        if (
            review.status is not ReviewStatus.AWAITING_HUMAN_DECISION
            or not review.can_request_human_decision
        ):
            raise ApprovalGateError("auditor-rejected plans cannot receive a human decision")

        base = {
            "decision_id": f"decision:{review.review_id}:{request.decision.value}",
            "case_id": review.case_id,
            "decision": request.decision,
            "decided_by": request.decided_by,
            "reason": request.reason,
        }
        if request.decision is HumanDecisionType.APPROVE:
            authorization = ExecutionAuthorization(
                authorization_id=f"authorization:{review.review_id}",
                review_id=review.review_id,
                case_id=review.case_id,
                plan_digest=review.plan_digest,
                approved_plan_ids=[action.plan_id for action in review.reviewed_actions],
                approved_actions=review.reviewed_actions,
                expected_state_changes=review.expected_state_changes,
                approved_by=request.decided_by,
            )
            return HumanDecisionResult(
                **base,
                status=ApprovalStatus.APPROVED,
                authorization=authorization,
                requires_re_review=False,
                execution_authorized=True,
            )
        if request.decision is HumanDecisionType.REJECT:
            return HumanDecisionResult(
                **base,
                status=ApprovalStatus.REJECTED,
                requires_re_review=False,
                execution_authorized=False,
            )

        actions = {action.plan_id: deepcopy(action) for action in review.reviewed_actions}
        if any(modification.plan_id not in actions for modification in request.modifications):
            raise ApprovalGateError("a modification references an unknown plan_id")
        if len({modification.plan_id for modification in request.modifications}) != len(
            request.modifications
        ):
            raise ApprovalGateError("each action may be modified only once per decision")
        for modification in request.modifications:
            action = actions[modification.plan_id]
            updates = {"arguments": deepcopy(modification.arguments)}
            if modification.item_ids is not None:
                updates["item_ids"] = modification.item_ids
            if modification.target_item_ids is not None:
                updates["target_item_ids"] = modification.target_item_ids
            actions[modification.plan_id] = action.model_copy(update=updates)
        revised_actions = sorted(actions.values(), key=lambda action: action.sequence)
        return HumanDecisionResult(
            **base,
            status=ApprovalStatus.MODIFICATION_REQUIRES_REVIEW,
            revised_actions=revised_actions,
            requires_re_review=True,
            execution_authorized=False,
        )

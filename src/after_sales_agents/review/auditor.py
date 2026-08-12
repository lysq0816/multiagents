"""Independent deterministic audit of candidate plans before human approval."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Iterable
from typing import Any

from after_sales_agents.domain.models import ActionType, AgentRole
from after_sales_agents.planning.models import (
    CandidateActionPlan,
    PlanningResult,
    PlanningWorkflowResult,
    PlanStatus,
)
from after_sales_agents.policy.models import (
    EligibilityStatus,
    FactField,
    FactSourceType,
    SourceFact,
)
from after_sales_agents.review.models import (
    AuditReviewRequest,
    AuditReviewResult,
    ExpectedStateChange,
    ReviewCheck,
    ReviewCheckStatus,
    ReviewCheckType,
    ReviewStatus,
)

EXPECTED_POLICY_BY_ACTION = {
    ActionType.CANCEL_ORDER: {
        "retail.identity.authentication",
        "retail.write.explicit_confirmation",
        "retail.cancel.pending_only",
        "retail.cancel.reason",
    },
    ActionType.CREATE_RETURN: {
        "retail.identity.authentication",
        "retail.write.explicit_confirmation",
        "retail.return.delivered_only",
        "retail.return.confirm_items",
        "retail.return.refund_method",
    },
    ActionType.EXCHANGE_ITEMS: {
        "retail.identity.authentication",
        "retail.write.explicit_confirmation",
        "retail.exchange.delivered_only",
        "retail.exchange.same_product_available",
        "retail.exchange.payment",
    },
}


def plan_digest(planning: PlanningWorkflowResult) -> str:
    payload = planning.model_dump(mode="json", exclude_none=False)
    for specialist_result in payload["specialist_results"]:
        specialist_result["order_handoff"].pop("created_at", None)
        specialist_result["policy_handoff"].pop("created_at", None)
        for fact in specialist_result["order_handoff"]["payload"]["facts"]:
            fact.pop("observed_at", None)
        for fact in specialist_result["policy_handoff"]["payload"]["facts"]:
            fact.pop("observed_at", None)
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class IndependentAuditor:
    role = AgentRole.AUDITOR

    def review(self, request: AuditReviewRequest) -> AuditReviewResult:
        planning = request.planning
        plan = planning.plan
        checks = [self._plan_gate_check(plan)]
        if plan.candidate_actions:
            checks.extend(
                (
                    self._entity_check(plan.candidate_actions, planning),
                    self._action_order_check(plan.candidate_actions),
                    self._evidence_check(plan.candidate_actions, planning),
                    self._policy_check(plan.candidate_actions, planning),
                    self._precondition_check(plan.candidate_actions, planning),
                )
            )
        all_passed = all(check.status is ReviewCheckStatus.PASSED for check in checks)
        status = (
            ReviewStatus.AWAITING_HUMAN_DECISION if all_passed else ReviewStatus.REJECTED_BY_AUDITOR
        )
        return AuditReviewResult(
            review_id=f"review:{plan.case_id}:{plan_digest(planning)[:12]}",
            case_id=plan.case_id,
            plan_digest=plan_digest(planning),
            status=status,
            checks=checks,
            reviewed_actions=plan.candidate_actions,
            expected_state_changes=(
                [self._expected_change(action) for action in plan.candidate_actions]
                if all_passed
                else []
            ),
            can_request_human_decision=all_passed,
        )

    @staticmethod
    def _plan_gate_check(plan: PlanningResult) -> ReviewCheck:
        passed = (
            plan.status is PlanStatus.READY_FOR_REVIEW
            and plan.can_advance_to_review
            and bool(plan.candidate_actions)
            and not plan.issues
        )
        return IndependentAuditor._check(
            check_id="audit:plan-gate",
            check_type=ReviewCheckType.PLAN_GATE,
            passed=passed,
            description=(
                "The planner marked the conflict-free plan ready for independent review."
                if passed
                else "The plan is not eligible for independent review."
            ),
            actions=plan.candidate_actions,
        )

    @staticmethod
    def _entity_check(
        actions: list[CandidateActionPlan],
        planning: PlanningWorkflowResult,
    ) -> ReviewCheck:
        handoffs = IndependentAuditor._handoffs_by_id(planning)
        specialist_results = {
            result.policy_handoff.handoff_id: result for result in planning.specialist_results
        }
        passed = all(
            action.case_id
            and action.order_id
            and action.plan_id
            and action.case_id == planning.plan.case_id
            and bool(action.source_handoff_ids)
            and all(
                handoff_id in handoffs
                and handoffs[handoff_id].case_id == action.case_id
                and handoffs[handoff_id].payload.order_id == action.order_id
                and handoffs[handoff_id].payload.action_type is action.action_type
                for handoff_id in action.source_handoff_ids
            )
            and all(
                handoff_id in specialist_results
                and IndependentAuditor._specialist_result_is_consistent(
                    specialist_results[handoff_id]
                )
                for handoff_id in action.source_handoff_ids
            )
            and (action.action_type is ActionType.CANCEL_ORDER or bool(action.item_ids))
            and (
                action.action_type is not ActionType.EXCHANGE_ITEMS
                or (
                    bool(action.target_item_ids)
                    and len(action.item_ids) == len(action.target_item_ids)
                )
            )
            for action in actions
        )
        return IndependentAuditor._check(
            check_id="audit:entities",
            check_type=ReviewCheckType.ENTITY,
            passed=passed,
            description=(
                "Every action has the required order and item entities."
                if passed
                else "At least one action has a missing or inconsistent order/item entity."
            ),
            actions=actions,
        )

    @staticmethod
    def _action_order_check(actions: list[CandidateActionPlan]) -> ReviewCheck:
        sequences = [action.sequence for action in actions]
        order_ids = [action.order_id for action in actions]
        passed = (
            sequences == list(range(1, len(actions) + 1))
            and len(sequences) == len(set(sequences))
            and len(order_ids) == len(set(order_ids))
        )
        return IndependentAuditor._check(
            check_id="audit:action-order",
            check_type=ReviewCheckType.ACTION_ORDER,
            passed=passed,
            description=(
                "Action sequence numbers are unique and contiguous, with one write per order."
                if passed
                else (
                    "Action sequence numbers are invalid or multiple sequential writes target "
                    "the same order."
                )
            ),
            actions=actions,
        )

    @staticmethod
    def _evidence_check(
        actions: list[CandidateActionPlan],
        planning: PlanningWorkflowResult,
    ) -> ReviewCheck:
        handoffs = IndependentAuditor._handoffs_by_id(planning)
        passed = all(
            bool(action.fact_ids)
            and len(action.fact_ids) == len(set(action.fact_ids))
            and bool(action.policy_clause_ids)
            and len(action.policy_clause_ids) == len(set(action.policy_clause_ids))
            and all(handoff_id in handoffs for handoff_id in action.source_handoff_ids)
            and set(action.fact_ids).issubset(
                {
                    fact.fact_id
                    for handoff_id in action.source_handoff_ids
                    if handoff_id in handoffs
                    for fact in handoffs[handoff_id].payload.facts
                }
            )
            and set(action.policy_clause_ids).issubset(
                {
                    hit.clause.clause_id
                    for handoff_id in action.source_handoff_ids
                    if handoff_id in handoffs
                    for hit in handoffs[handoff_id].payload.retrieved_policy
                }
            )
            for action in actions
        )
        return IndependentAuditor._check(
            check_id="audit:evidence",
            check_type=ReviewCheckType.EVIDENCE,
            passed=passed,
            description=(
                "Every action has unique fact and policy citations."
                if passed
                else "At least one action lacks usable fact or policy citations."
            ),
            actions=actions,
        )

    @staticmethod
    def _policy_check(
        actions: list[CandidateActionPlan],
        planning: PlanningWorkflowResult,
    ) -> ReviewCheck:
        handoffs = IndependentAuditor._handoffs_by_id(planning)
        missing = {
            action.plan_id: sorted(
                EXPECTED_POLICY_BY_ACTION[action.action_type] - set(action.policy_clause_ids)
            )
            for action in actions
        }
        missing = {plan_id: clauses for plan_id, clauses in missing.items() if clauses}
        passed = not missing and all(
            all(
                handoff_id in handoffs
                and handoffs[handoff_id].payload.decision.status is EligibilityStatus.ELIGIBLE
                and set(action.policy_clause_ids)
                == set(handoffs[handoff_id].payload.decision.conclusion.policy_clause_ids)
                for handoff_id in action.source_handoff_ids
            )
            for action in actions
        )
        return IndependentAuditor._check(
            check_id="audit:policy",
            check_type=ReviewCheckType.POLICY,
            passed=passed,
            description=(
                "Every action cites all mandatory policy clauses."
                if passed
                else f"Mandatory policy citations are missing: {missing}."
            ),
            actions=actions,
        )

    @staticmethod
    def _precondition_check(
        actions: list[CandidateActionPlan],
        planning: PlanningWorkflowResult,
    ) -> ReviewCheck:
        handoffs = IndependentAuditor._handoffs_by_id(planning)
        passed = all(
            IndependentAuditor._valid_arguments(action)
            and IndependentAuditor._arguments_match_source_facts(action, handoffs)
            for action in actions
        )
        return IndependentAuditor._check(
            check_id="audit:preconditions",
            check_type=ReviewCheckType.PRECONDITION,
            passed=passed,
            description=(
                "Every action has the exact write-tool arguments required by its type."
                if passed
                else "At least one action is missing or contains invalid write-tool arguments."
            ),
            actions=actions,
        )

    @staticmethod
    def _valid_arguments(action: CandidateActionPlan) -> bool:
        arguments = action.arguments
        if action.action_type is ActionType.CANCEL_ORDER:
            return set(arguments) == {"reason"} and arguments["reason"] in {
                "no longer needed",
                "ordered by mistake",
            }
        if action.action_type is ActionType.CREATE_RETURN:
            return (
                set(arguments) == {"item_ids", "payment_method_id"}
                and Counter(arguments["item_ids"]) == Counter(action.item_ids)
                and bool(arguments["payment_method_id"])
            )
        return (
            set(arguments) == {"item_ids", "new_item_ids", "payment_method_id"}
            and Counter(arguments["item_ids"]) == Counter(action.item_ids)
            and Counter(arguments["new_item_ids"]) == Counter(action.target_item_ids)
            and len(arguments["item_ids"]) == len(arguments["new_item_ids"])
            and bool(arguments["payment_method_id"])
        )

    @staticmethod
    def _arguments_match_source_facts(
        action: CandidateActionPlan,
        handoffs: dict[str, Any],
    ) -> bool:
        source_handoffs = [
            handoffs[handoff_id]
            for handoff_id in action.source_handoff_ids
            if handoff_id in handoffs
        ]
        if len(source_handoffs) != len(action.source_handoff_ids):
            return False
        fact_sets = [
            {fact.field: fact for fact in handoff.payload.facts} for handoff in source_handoffs
        ]
        return all(
            IndependentAuditor._arguments_match_fact_set(action, facts) for facts in fact_sets
        )

    @staticmethod
    def _arguments_match_fact_set(
        action: CandidateActionPlan,
        facts: dict[FactField, SourceFact],
    ) -> bool:
        expected_status = (
            "pending" if action.action_type is ActionType.CANCEL_ORDER else "delivered"
        )
        status = facts.get(FactField.ORDER_STATUS)
        if status is None or status.value != expected_status:
            return False
        arguments = action.arguments
        if action.action_type is ActionType.CANCEL_ORDER:
            reason = facts.get(FactField.CANCEL_REASON)
            return reason is not None and arguments["reason"] == reason.value
        item_fact = facts.get(FactField.ITEM_IDS)
        payment_fact = facts.get(FactField.PAYMENT_METHOD_ID)
        if (
            item_fact is None
            or payment_fact is None
            or Counter(arguments["item_ids"]) != Counter(item_fact.value)
            or arguments["payment_method_id"] != payment_fact.value
        ):
            return False
        if action.action_type is ActionType.CREATE_RETURN:
            return True
        target_fact = facts.get(FactField.TARGET_ITEM_IDS)
        return target_fact is not None and Counter(arguments["new_item_ids"]) == Counter(
            target_fact.value
        )

    @staticmethod
    def _handoffs_by_id(planning: PlanningWorkflowResult) -> dict[str, Any]:
        return {
            result.policy_handoff.handoff_id: result.policy_handoff
            for result in planning.specialist_results
        }

    @staticmethod
    def _specialist_result_is_consistent(result: Any) -> bool:
        order_handoff = result.order_handoff
        policy_handoff = result.policy_handoff
        order_payload = order_handoff.payload
        policy_payload = policy_handoff.payload
        if (
            order_handoff.case_id != policy_handoff.case_id
            or order_payload.case_id != policy_payload.case_id
            or order_payload.action_type is not policy_payload.action_type
            or order_payload.order_id != policy_payload.order_id
            or [fact.model_dump(mode="json") for fact in order_payload.facts]
            != [fact.model_dump(mode="json") for fact in policy_payload.facts]
            or any(fact.subject_id != order_payload.order_id for fact in order_payload.facts)
        ):
            return False
        call_ids = [call.call_id for call in order_payload.tool_calls]
        if len(call_ids) != len(set(call_ids)):
            return False
        if any(
            call.actor is not AgentRole.ORDER_SPECIALIST
            or call.tool_name not in {"get_order_details", "get_product_details"}
            for call in order_payload.tool_calls
        ):
            return False
        order_status = next(
            (fact for fact in order_payload.facts if fact.field is FactField.ORDER_STATUS),
            None,
        )
        return bool(
            order_status
            and order_status.source_type is FactSourceType.TOOL
            and any(
                call.call_id == order_status.source_id
                and call.tool_name == "get_order_details"
                and call.arguments == {"order_id": order_payload.order_id}
                for call in order_payload.tool_calls
            )
        )

    @staticmethod
    def _expected_change(action: CandidateActionPlan) -> ExpectedStateChange:
        if action.action_type is ActionType.CANCEL_ORDER:
            return ExpectedStateChange(
                order_id=action.order_id,
                expected_status="cancelled",
                expected_fields={"cancel_reason": action.arguments["reason"]},
            )
        if action.action_type is ActionType.CREATE_RETURN:
            return ExpectedStateChange(
                order_id=action.order_id,
                expected_status="return requested",
                expected_fields={
                    "return_items": sorted(action.item_ids),
                    "return_payment_method_id": action.arguments["payment_method_id"],
                },
            )
        return ExpectedStateChange(
            order_id=action.order_id,
            expected_status="exchange requested",
            expected_fields={
                "exchange_items": sorted(action.item_ids),
                "exchange_new_items": sorted(action.target_item_ids),
                "exchange_payment_method_id": action.arguments["payment_method_id"],
            },
        )

    @staticmethod
    def _check(
        *,
        check_id: str,
        check_type: ReviewCheckType,
        passed: bool,
        description: str,
        actions: Iterable[CandidateActionPlan],
    ) -> ReviewCheck:
        action_list = list(actions)
        return ReviewCheck(
            check_id=check_id,
            check_type=check_type,
            status=(ReviewCheckStatus.PASSED if passed else ReviewCheckStatus.FAILED),
            description=description,
            plan_ids=[action.plan_id for action in action_list],
            fact_ids=list(
                dict.fromkeys(fact_id for action in action_list for fact_id in action.fact_ids)
            ),
            policy_clause_ids=list(
                dict.fromkeys(
                    clause_id for action in action_list for clause_id in action.policy_clause_ids
                )
            ),
        )

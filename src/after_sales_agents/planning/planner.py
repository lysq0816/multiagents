"""Deterministic aggregation and conflict detection for specialist conclusions."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from after_sales_agents.agents.models import PolicyToPlannerHandoff
from after_sales_agents.domain.models import ActionType, AgentRole
from after_sales_agents.planning.models import (
    CandidateActionPlan,
    ConflictType,
    PlannerRequest,
    PlanningIssue,
    PlanningIssueSeverity,
    PlanningResult,
    PlanStatus,
)
from after_sales_agents.policy.models import EligibilityStatus, FactField, SourceFact


class CandidateActionPlanner:
    """Build reviewable plans without invoking tools or changing business state."""

    role = AgentRole.PLANNER

    def plan(self, request: PlannerRequest) -> PlanningResult:
        issues: list[PlanningIssue] = []
        questions: list[str] = []
        candidates: list[CandidateActionPlan] = []

        self._add_decision_issues(request.handoffs, issues, questions)
        self._add_cross_handoff_conflicts(request.handoffs, issues, questions)

        seen_actions: dict[
            tuple[str, ActionType, tuple[str, ...], tuple[str, ...]], CandidateActionPlan
        ] = {}
        for handoff in request.handoffs:
            if handoff.payload.decision.status is not EligibilityStatus.ELIGIBLE:
                continue
            candidate = self._build_candidate(handoff, sequence=len(candidates) + 1)
            key = (
                candidate.order_id,
                candidate.action_type,
                tuple(sorted(candidate.item_ids)),
                tuple(sorted(candidate.target_item_ids)),
            )
            existing = seen_actions.get(key)
            if existing is None:
                seen_actions[key] = candidate
                candidates.append(candidate)
            else:
                existing.source_handoff_ids.append(handoff.handoff_id)

        if any(issue.severity is PlanningIssueSeverity.BLOCKING for issue in issues):
            status = PlanStatus.BLOCKED
        elif issues:
            status = PlanStatus.NEEDS_CLARIFICATION
        else:
            status = PlanStatus.READY_FOR_REVIEW

        return PlanningResult(
            case_id=request.case_id,
            status=status,
            candidate_actions=candidates,
            issues=issues,
            clarification_questions=list(dict.fromkeys(questions)),
            can_advance_to_review=status is PlanStatus.READY_FOR_REVIEW,
        )

    def _add_decision_issues(
        self,
        handoffs: list[PolicyToPlannerHandoff],
        issues: list[PlanningIssue],
        questions: list[str],
    ) -> None:
        for handoff in handoffs:
            decision = handoff.payload.decision
            if decision.status is EligibilityStatus.INSUFFICIENT_FACTS:
                fields = [field.value for field in decision.missing_fact_fields]
                issues.append(
                    PlanningIssue(
                        issue_id=f"issue:{handoff.handoff_id}:missing-information",
                        conflict_type=ConflictType.MISSING_INFORMATION,
                        severity=PlanningIssueSeverity.NEEDS_CLARIFICATION,
                        description=(
                            f"{handoff.payload.action_type.value} lacks required source facts."
                        ),
                        handoff_ids=[handoff.handoff_id],
                        fact_ids=decision.conclusion.fact_ids,
                        policy_clause_ids=decision.conclusion.policy_clause_ids,
                        fields=fields,
                    )
                )
                questions.extend(
                    f"Please provide or verify the required field: {field.value}."
                    for field in decision.missing_fact_fields
                )
            elif decision.status is EligibilityStatus.INELIGIBLE:
                issues.append(
                    PlanningIssue(
                        issue_id=f"issue:{handoff.handoff_id}:policy-ineligible",
                        conflict_type=ConflictType.POLICY,
                        severity=PlanningIssueSeverity.BLOCKING,
                        description=(
                            f"Policy requirements reject {handoff.payload.action_type.value} "
                            f"for order {handoff.payload.order_id}."
                        ),
                        handoff_ids=[handoff.handoff_id],
                        fact_ids=decision.conclusion.fact_ids,
                        policy_clause_ids=decision.conclusion.policy_clause_ids,
                    )
                )

    def _add_cross_handoff_conflicts(
        self,
        handoffs: list[PolicyToPlannerHandoff],
        issues: list[PlanningIssue],
        questions: list[str],
    ) -> None:
        by_order: dict[str, list[PolicyToPlannerHandoff]] = defaultdict(list)
        by_operation: dict[
            tuple[str, ActionType, tuple[str, ...], tuple[str, ...]],
            list[PolicyToPlannerHandoff],
        ] = defaultdict(list)
        for handoff in handoffs:
            by_order[handoff.payload.order_id].append(handoff)
            item_ids, target_item_ids = self._operation_signature(handoff)
            by_operation[
                (
                    handoff.payload.order_id,
                    handoff.payload.action_type,
                    item_ids,
                    target_item_ids,
                )
            ].append(handoff)

        for order_id, order_handoffs in by_order.items():
            self._detect_order_status_conflict(order_id, order_handoffs, issues)
            self._detect_order_action_conflict(order_id, order_handoffs, issues)
            self._detect_item_conflict(order_id, order_handoffs, issues)

        for (
            order_id,
            action_type,
            _item_ids,
            _target_item_ids,
        ), action_handoffs in by_operation.items():
            self._detect_duplicate_action(order_id, action_type, action_handoffs, issues, questions)
            self._detect_amount_conflict(order_id, action_type, action_handoffs, issues, questions)
            self._detect_policy_conflict(order_id, action_type, action_handoffs, issues)

    def _detect_order_status_conflict(
        self,
        order_id: str,
        handoffs: list[PolicyToPlannerHandoff],
        issues: list[PlanningIssue],
    ) -> None:
        facts = self._facts_for_field(handoffs, FactField.ORDER_STATUS)
        if len({self._stable_value(fact.value) for fact in facts}) <= 1:
            return
        issues.append(
            self._issue(
                suffix=f"{order_id}:order-status",
                conflict_type=ConflictType.ORDER,
                description=f"Order {order_id} has conflicting status snapshots.",
                handoffs=handoffs,
                facts=facts,
            )
        )

    def _detect_order_action_conflict(
        self,
        order_id: str,
        handoffs: list[PolicyToPlannerHandoff],
        issues: list[PlanningIssue],
    ) -> None:
        action_types = {handoff.payload.action_type for handoff in handoffs}
        if ActionType.CANCEL_ORDER not in action_types or not action_types.intersection(
            {ActionType.CREATE_RETURN, ActionType.EXCHANGE_ITEMS}
        ):
            return
        issues.append(
            self._issue(
                suffix=f"{order_id}:incompatible-actions",
                conflict_type=ConflictType.ORDER,
                description=(
                    f"Order {order_id} cannot be cancelled and returned or exchanged "
                    "in the same plan."
                ),
                handoffs=handoffs,
                facts=self._facts_for_field(handoffs, FactField.ORDER_STATUS),
            )
        )

    def _detect_item_conflict(
        self,
        order_id: str,
        handoffs: list[PolicyToPlannerHandoff],
        issues: list[PlanningIssue],
    ) -> None:
        returns = [
            handoff
            for handoff in handoffs
            if handoff.payload.action_type is ActionType.CREATE_RETURN
        ]
        exchanges = [
            handoff
            for handoff in handoffs
            if handoff.payload.action_type is ActionType.EXCHANGE_ITEMS
        ]
        return_items = self._item_ids(returns)
        exchange_items = self._item_ids(exchanges)
        overlap = sorted(return_items & exchange_items)
        if not overlap:
            return
        involved = [*returns, *exchanges]
        issues.append(
            self._issue(
                suffix=f"{order_id}:item-overlap",
                conflict_type=ConflictType.ITEM,
                description=(
                    f"Items {', '.join(overlap)} are requested for both return and exchange "
                    f"on order {order_id}."
                ),
                handoffs=involved,
                facts=self._facts_for_field(involved, FactField.ITEM_IDS),
            )
        )

    def _detect_duplicate_action(
        self,
        order_id: str,
        action_type: ActionType,
        handoffs: list[PolicyToPlannerHandoff],
        issues: list[PlanningIssue],
        questions: list[str],
    ) -> None:
        if len(handoffs) <= 1:
            return
        issues.append(
            PlanningIssue(
                issue_id=f"issue:{order_id}:{action_type.value}:duplicate",
                conflict_type=ConflictType.DUPLICATE_ACTION,
                severity=PlanningIssueSeverity.NEEDS_CLARIFICATION,
                description=(
                    f"Order {order_id} has multiple {action_type.value} conclusions; "
                    "confirm whether they describe one action."
                ),
                handoff_ids=[handoff.handoff_id for handoff in handoffs],
            )
        )
        questions.append(
            f"Should the duplicate {action_type.value} requests for order {order_id} be merged?"
        )

    def _detect_amount_conflict(
        self,
        order_id: str,
        action_type: ActionType,
        handoffs: list[PolicyToPlannerHandoff],
        issues: list[PlanningIssue],
        questions: list[str],
    ) -> None:
        amount_facts = self._facts_for_field(handoffs, FactField.PRICE_DIFFERENCE)
        if len({self._stable_value(fact.value) for fact in amount_facts}) <= 1:
            return
        issues.append(
            PlanningIssue(
                issue_id=f"issue:{order_id}:{action_type.value}:amount",
                conflict_type=ConflictType.AMOUNT,
                severity=PlanningIssueSeverity.NEEDS_CLARIFICATION,
                description=(
                    f"Order {order_id} has conflicting price differences for {action_type.value}."
                ),
                handoff_ids=[handoff.handoff_id for handoff in handoffs],
                fact_ids=[fact.fact_id for fact in amount_facts],
                fields=[FactField.PRICE_DIFFERENCE.value],
            )
        )
        questions.append(
            f"What is the verified price difference for {action_type.value} on order {order_id}?"
        )

    def _detect_policy_conflict(
        self,
        order_id: str,
        action_type: ActionType,
        handoffs: list[PolicyToPlannerHandoff],
        issues: list[PlanningIssue],
    ) -> None:
        statuses = {handoff.payload.decision.status for handoff in handoffs}
        if len(statuses) <= 1:
            return
        issues.append(
            PlanningIssue(
                issue_id=f"issue:{order_id}:{action_type.value}:policy",
                conflict_type=ConflictType.POLICY,
                severity=PlanningIssueSeverity.BLOCKING,
                description=(
                    f"Specialist conclusions disagree on policy eligibility for "
                    f"{action_type.value} on order {order_id}."
                ),
                handoff_ids=[handoff.handoff_id for handoff in handoffs],
                fact_ids=list(
                    dict.fromkeys(
                        fact_id
                        for handoff in handoffs
                        for fact_id in handoff.payload.decision.conclusion.fact_ids
                    )
                ),
                policy_clause_ids=list(
                    dict.fromkeys(
                        clause_id
                        for handoff in handoffs
                        for clause_id in handoff.payload.decision.conclusion.policy_clause_ids
                    )
                ),
            )
        )

    @staticmethod
    def _build_candidate(
        handoff: PolicyToPlannerHandoff,
        *,
        sequence: int,
    ) -> CandidateActionPlan:
        payload = handoff.payload
        facts = {fact.field: fact for fact in payload.facts}
        item_ids = CandidateActionPlanner._list_value(facts.get(FactField.ITEM_IDS))
        target_item_ids = CandidateActionPlanner._list_value(facts.get(FactField.TARGET_ITEM_IDS))
        arguments: dict[str, Any] = {}
        if payload.action_type is ActionType.CANCEL_ORDER:
            CandidateActionPlanner._copy_fact_value(
                facts, FactField.CANCEL_REASON, arguments, "reason"
            )
        elif payload.action_type is ActionType.CREATE_RETURN:
            arguments["item_ids"] = item_ids
            CandidateActionPlanner._copy_fact_value(
                facts, FactField.PAYMENT_METHOD_ID, arguments, "payment_method_id"
            )
        else:
            arguments["item_ids"] = item_ids
            arguments["new_item_ids"] = target_item_ids
            CandidateActionPlanner._copy_fact_value(
                facts, FactField.PAYMENT_METHOD_ID, arguments, "payment_method_id"
            )

        decision = payload.decision
        return CandidateActionPlan(
            plan_id=f"plan:{handoff.handoff_id}",
            sequence=sequence,
            case_id=handoff.case_id,
            source_handoff_ids=[handoff.handoff_id],
            action_type=payload.action_type,
            order_id=payload.order_id,
            item_ids=item_ids,
            target_item_ids=target_item_ids,
            arguments=arguments,
            fact_ids=decision.conclusion.fact_ids,
            policy_clause_ids=decision.conclusion.policy_clause_ids,
        )

    @staticmethod
    def _copy_fact_value(
        facts: dict[FactField, SourceFact],
        field: FactField,
        target: dict[str, Any],
        key: str,
    ) -> None:
        fact = facts.get(field)
        if fact is not None:
            target[key] = fact.value

    @staticmethod
    def _list_value(fact: SourceFact | None) -> list[str]:
        if fact is None or not isinstance(fact.value, list):
            return []
        return [str(value) for value in fact.value]

    @staticmethod
    def _facts_for_field(
        handoffs: Iterable[PolicyToPlannerHandoff], field: FactField
    ) -> list[SourceFact]:
        return [
            fact for handoff in handoffs for fact in handoff.payload.facts if fact.field is field
        ]

    @staticmethod
    def _item_ids(handoffs: Iterable[PolicyToPlannerHandoff]) -> set[str]:
        return {
            str(item_id)
            for fact in CandidateActionPlanner._facts_for_field(handoffs, FactField.ITEM_IDS)
            if isinstance(fact.value, list)
            for item_id in fact.value
        }

    @staticmethod
    def _operation_signature(
        handoff: PolicyToPlannerHandoff,
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        facts = {fact.field: fact for fact in handoff.payload.facts}
        return (
            tuple(sorted(CandidateActionPlanner._list_value(facts.get(FactField.ITEM_IDS)))),
            tuple(sorted(CandidateActionPlanner._list_value(facts.get(FactField.TARGET_ITEM_IDS)))),
        )

    @staticmethod
    def _stable_value(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)

    @staticmethod
    def _issue(
        *,
        suffix: str,
        conflict_type: ConflictType,
        description: str,
        handoffs: list[PolicyToPlannerHandoff],
        facts: list[SourceFact],
    ) -> PlanningIssue:
        return PlanningIssue(
            issue_id=f"issue:{suffix}",
            conflict_type=conflict_type,
            severity=PlanningIssueSeverity.BLOCKING,
            description=description,
            handoff_ids=[handoff.handoff_id for handoff in handoffs],
            fact_ids=[fact.fact_id for fact in facts],
            fields=list(dict.fromkeys(fact.field.value for fact in facts)),
        )

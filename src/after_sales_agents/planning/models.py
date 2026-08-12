"""Typed inputs and outputs for deterministic candidate-action planning."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from after_sales_agents.agents.models import (
    CollaborationReviewRequest,
    PolicyToPlannerHandoff,
    SpecialistCollaborationResult,
)
from after_sales_agents.domain.models import ActionType


class ConflictType(StrEnum):
    ORDER = "order"
    ITEM = "item"
    AMOUNT = "amount"
    POLICY = "policy"
    DUPLICATE_ACTION = "duplicate_action"
    MISSING_INFORMATION = "missing_information"


class PlanningIssueSeverity(StrEnum):
    NEEDS_CLARIFICATION = "needs_clarification"
    BLOCKING = "blocking"


class PlanStatus(StrEnum):
    READY_FOR_REVIEW = "ready_for_review"
    NEEDS_CLARIFICATION = "needs_clarification"
    BLOCKED = "blocked"


class PlanningIssue(BaseModel):
    issue_id: str = Field(min_length=1)
    conflict_type: ConflictType
    severity: PlanningIssueSeverity
    description: str = Field(min_length=1)
    handoff_ids: list[str] = Field(min_length=1)
    fact_ids: list[str] = Field(default_factory=list)
    policy_clause_ids: list[str] = Field(default_factory=list)
    fields: list[str] = Field(default_factory=list)


class CandidateActionPlan(BaseModel):
    plan_id: str = Field(min_length=1)
    sequence: int = Field(ge=1)
    case_id: str = Field(min_length=1)
    source_handoff_ids: list[str] = Field(min_length=1)
    action_type: ActionType
    order_id: str = Field(min_length=1)
    item_ids: list[str] = Field(default_factory=list)
    target_item_ids: list[str] = Field(default_factory=list)
    arguments: dict[str, Any] = Field(default_factory=dict)
    fact_ids: list[str] = Field(min_length=1)
    policy_clause_ids: list[str] = Field(min_length=1)
    requires_approval: Literal[True] = True
    can_execute: Literal[False] = False

    @model_validator(mode="after")
    def require_a_supported_write_action(self) -> CandidateActionPlan:
        if self.action_type not in {
            ActionType.CANCEL_ORDER,
            ActionType.CREATE_RETURN,
            ActionType.EXCHANGE_ITEMS,
        }:
            raise ValueError("candidate plans support only cancel, return, and exchange")
        return self


class PlannerRequest(BaseModel):
    case_id: str = Field(min_length=1)
    handoffs: list[PolicyToPlannerHandoff] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_handoffs(self) -> PlannerRequest:
        handoff_ids = [handoff.handoff_id for handoff in self.handoffs]
        if len(handoff_ids) != len(set(handoff_ids)):
            raise ValueError("planner handoff IDs must be unique")
        if any(handoff.case_id != self.case_id for handoff in self.handoffs):
            raise ValueError("every planner handoff must belong to case_id")
        return self


class PlanningResult(BaseModel):
    case_id: str = Field(min_length=1)
    status: PlanStatus
    candidate_actions: list[CandidateActionPlan] = Field(default_factory=list)
    issues: list[PlanningIssue] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)
    can_advance_to_review: bool
    can_execute: Literal[False] = False

    @model_validator(mode="after")
    def validate_gate_state(self) -> PlanningResult:
        ready = self.status is PlanStatus.READY_FOR_REVIEW
        if self.can_advance_to_review is not ready:
            raise ValueError("only ready plans may advance to independent review")
        if ready and not self.candidate_actions:
            raise ValueError("ready plans require at least one candidate action")
        if self.status is PlanStatus.BLOCKED and not any(
            issue.severity is PlanningIssueSeverity.BLOCKING for issue in self.issues
        ):
            raise ValueError("blocked plans require a blocking issue")
        return self


class PlanningWorkflowRequest(BaseModel):
    reviews: list[CollaborationReviewRequest] = Field(min_length=1)

    @model_validator(mode="after")
    def require_one_case(self) -> PlanningWorkflowRequest:
        case_ids = {review.analysis.case_id for review in self.reviews}
        if len(case_ids) != 1:
            raise ValueError("all specialist reviews must belong to one case")
        return self


class PlanningWorkflowResult(BaseModel):
    specialist_results: list[SpecialistCollaborationResult] = Field(min_length=1)
    plan: PlanningResult

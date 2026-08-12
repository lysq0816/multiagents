"""Typed review, human decision, authorization, and verification records."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from after_sales_agents.domain.models import AgentRole
from after_sales_agents.planning.models import (
    CandidateActionPlan,
    PlanningWorkflowResult,
)


class ReviewCheckType(StrEnum):
    PLAN_GATE = "plan_gate"
    ENTITY = "entity"
    ACTION_ORDER = "action_order"
    EVIDENCE = "evidence"
    POLICY = "policy"
    PRECONDITION = "precondition"


class ReviewCheckStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"


class ReviewStatus(StrEnum):
    AWAITING_HUMAN_DECISION = "awaiting_human_decision"
    REJECTED_BY_AUDITOR = "rejected_by_auditor"


class HumanDecisionType(StrEnum):
    APPROVE = "approve"
    MODIFY = "modify"
    REJECT = "reject"


class ApprovalStatus(StrEnum):
    APPROVED = "approved"
    MODIFICATION_REQUIRES_REVIEW = "modification_requires_review"
    REJECTED = "rejected"


class ExpectedStateChange(BaseModel):
    order_id: str = Field(min_length=1)
    expected_status: str = Field(min_length=1)
    expected_fields: dict[str, Any] = Field(default_factory=dict)


class ReviewCheck(BaseModel):
    check_id: str = Field(min_length=1)
    check_type: ReviewCheckType
    status: ReviewCheckStatus
    description: str = Field(min_length=1)
    plan_ids: list[str] = Field(default_factory=list)
    fact_ids: list[str] = Field(default_factory=list)
    policy_clause_ids: list[str] = Field(default_factory=list)


class AuditReviewRequest(BaseModel):
    planning: PlanningWorkflowResult


class AuditReviewResult(BaseModel):
    review_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    actor: Literal[AgentRole.AUDITOR] = AgentRole.AUDITOR
    plan_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: ReviewStatus
    checks: list[ReviewCheck] = Field(min_length=1)
    reviewed_actions: list[CandidateActionPlan] = Field(default_factory=list)
    expected_state_changes: list[ExpectedStateChange] = Field(default_factory=list)
    can_request_human_decision: bool
    can_execute: Literal[False] = False
    reviewed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_review_gate(self) -> AuditReviewResult:
        all_passed = all(check.status is ReviewCheckStatus.PASSED for check in self.checks)
        awaiting = self.status is ReviewStatus.AWAITING_HUMAN_DECISION
        if awaiting is not all_passed:
            raise ValueError("only a fully passed review may await a human decision")
        if self.can_request_human_decision is not awaiting:
            raise ValueError("human decisions are allowed only after a passed audit")
        if any(action.case_id != self.case_id for action in self.reviewed_actions):
            raise ValueError("reviewed actions must belong to the review case")
        plan_ids = [action.plan_id for action in self.reviewed_actions]
        if len(plan_ids) != len(set(plan_ids)):
            raise ValueError("reviewed action plan IDs must be unique")
        if awaiting and (
            not self.reviewed_actions
            or len(self.expected_state_changes) != len(self.reviewed_actions)
        ):
            raise ValueError("passed reviews require one expected state per action")
        if not awaiting and self.expected_state_changes:
            raise ValueError("auditor-rejected reviews cannot predict executable changes")
        if awaiting and [change.order_id for change in self.expected_state_changes] != [
            action.order_id for action in self.reviewed_actions
        ]:
            raise ValueError("expected state order IDs must match reviewed actions")
        return self


class ActionModification(BaseModel):
    plan_id: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    item_ids: list[str] | None = None
    target_item_ids: list[str] | None = None


class HumanDecisionRequest(BaseModel):
    planning: PlanningWorkflowResult
    review: AuditReviewResult
    decision: HumanDecisionType
    decided_by: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    modifications: list[ActionModification] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_decision_payload(self) -> HumanDecisionRequest:
        if self.planning.plan.case_id != self.review.case_id:
            raise ValueError("planning and review must belong to the same case")
        if self.decision is HumanDecisionType.MODIFY and not self.modifications:
            raise ValueError("modify decisions require at least one modification")
        if self.decision is not HumanDecisionType.MODIFY and self.modifications:
            raise ValueError("only modify decisions may include modifications")
        return self


class ExecutionAuthorization(BaseModel):
    authorization_id: str = Field(min_length=1)
    review_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    plan_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    approved_plan_ids: list[str] = Field(min_length=1)
    approved_actions: list[CandidateActionPlan] = Field(min_length=1)
    expected_state_changes: list[ExpectedStateChange] = Field(min_length=1)
    approved_by: str = Field(min_length=1)
    single_use: Literal[True] = True
    authorizes_execution: Literal[True] = True
    write_executed: Literal[False] = False
    issued_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_authorized_actions(self) -> ExecutionAuthorization:
        action_ids = [action.plan_id for action in self.approved_actions]
        if self.approved_plan_ids != action_ids or len(action_ids) != len(set(action_ids)):
            raise ValueError("approved plan IDs must exactly match unique approved actions")
        if any(action.case_id != self.case_id for action in self.approved_actions):
            raise ValueError("approved actions must belong to the authorization case")
        if len(self.expected_state_changes) != len(self.approved_actions):
            raise ValueError("authorization requires one expected state per action")
        if [change.order_id for change in self.expected_state_changes] != [
            action.order_id for action in self.approved_actions
        ]:
            raise ValueError("authorized expected states must match approved action orders")
        return self


class HumanDecisionResult(BaseModel):
    decision_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    decision: HumanDecisionType
    status: ApprovalStatus
    decided_by: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    authorization: ExecutionAuthorization | None = None
    revised_actions: list[CandidateActionPlan] = Field(default_factory=list)
    requires_re_review: bool
    execution_authorized: bool
    can_execute_now: Literal[False] = False
    write_executed: Literal[False] = False
    decided_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_decision_gate(self) -> HumanDecisionResult:
        approved = self.status is ApprovalStatus.APPROVED
        if (self.authorization is not None) is not approved:
            raise ValueError("only approval produces an execution authorization")
        if self.execution_authorized is not approved:
            raise ValueError("only approval may authorize future execution")
        modified = self.status is ApprovalStatus.MODIFICATION_REQUIRES_REVIEW
        if self.requires_re_review is not modified:
            raise ValueError("only modified actions require re-review")
        if modified and not self.revised_actions:
            raise ValueError("modified decisions require revised actions")
        if not modified and self.revised_actions:
            raise ValueError("only modified decisions may contain revised actions")
        return self


class StateVerificationStatus(StrEnum):
    MATCHED = "matched"
    MISMATCH = "mismatch"
    NOT_EXECUTED = "not_executed"


class StateDifference(BaseModel):
    path: str = Field(min_length=1)
    expected: Any
    actual: Any


class StateVerificationRequest(BaseModel):
    authorization: ExecutionAuthorization
    before_snapshots: dict[str, dict[str, Any]] = Field(min_length=1)
    after_snapshots: dict[str, dict[str, Any]] = Field(min_length=1)


class StateVerificationResult(BaseModel):
    verification_id: str = Field(min_length=1)
    authorization_id: str = Field(min_length=1)
    status: StateVerificationStatus
    differences: list[StateDifference] = Field(default_factory=list)
    verified_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_differences(self) -> StateVerificationResult:
        matched = self.status is StateVerificationStatus.MATCHED
        if matched == bool(self.differences):
            raise ValueError("matched verification has no differences; other states require them")
        return self

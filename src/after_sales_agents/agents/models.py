"""Structured messages exchanged by the Day 4 specialist agents."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from after_sales_agents.domain.models import ActionType, AgentRole
from after_sales_agents.policy.models import (
    EligibilityDecision,
    FactField,
    PolicySearchHit,
    SourceFact,
)


class ToolCallRecord(BaseModel):
    call_id: str = Field(min_length=1)
    actor: AgentRole
    tool_name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolCallResult(BaseModel):
    call: ToolCallRecord
    data: dict[str, Any]


class ExchangeTargetRequest(BaseModel):
    product_id: str = Field(min_length=1)
    current_item_id: str = Field(min_length=1)
    target_item_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def require_a_different_target(self) -> ExchangeTargetRequest:
        if self.current_item_id == self.target_item_id:
            raise ValueError("exchange target must differ from the current item")
        return self


class OrderSpecialistRequest(BaseModel):
    case_id: str = Field(min_length=1)
    action_type: ActionType
    order_id: str = Field(min_length=1)
    provided_facts: list[SourceFact] = Field(default_factory=list)
    exchange_targets: list[ExchangeTargetRequest] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_action_and_provided_facts(self) -> OrderSpecialistRequest:
        supported = {
            ActionType.CANCEL_ORDER,
            ActionType.CREATE_RETURN,
            ActionType.EXCHANGE_ITEMS,
        }
        if self.action_type not in supported:
            raise ValueError("order specialist supports cancel, return, and exchange")
        fact_ids = [fact.fact_id for fact in self.provided_facts]
        fields = [fact.field for fact in self.provided_facts]
        if len(fact_ids) != len(set(fact_ids)) or len(fields) != len(set(fields)):
            raise ValueError("provided facts must have unique IDs and fields")
        if FactField.ORDER_STATUS in fields:
            raise ValueError("order.status must come from the order read tool")
        derived_exchange_fields = {
            FactField.TARGET_ITEM_IDS,
            FactField.TARGET_ITEMS_AVAILABLE,
            FactField.TARGET_ITEMS_SAME_PRODUCT,
            FactField.TARGET_ITEMS_DIFFERENT_OPTION,
        }
        if derived_exchange_fields & set(fields):
            raise ValueError("exchange target facts must come from product read tools")
        if self.exchange_targets and self.action_type is not ActionType.EXCHANGE_ITEMS:
            raise ValueError("exchange targets are valid only for exchange actions")
        return self


class OrderFactBundle(BaseModel):
    case_id: str = Field(min_length=1)
    action_type: ActionType
    order_id: str = Field(min_length=1)
    facts: list[SourceFact] = Field(min_length=1)
    tool_calls: list[ToolCallRecord] = Field(min_length=1)


class OrderToPolicyHandoff(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    handoff_type: Literal["order_facts"] = "order_facts"
    handoff_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    sender: Literal[AgentRole.ORDER_SPECIALIST] = AgentRole.ORDER_SPECIALIST
    recipient: Literal[AgentRole.POLICY_SPECIALIST] = AgentRole.POLICY_SPECIALIST
    payload: OrderFactBundle
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_case_identity(self) -> OrderToPolicyHandoff:
        if self.case_id != self.payload.case_id:
            raise ValueError("handoff case_id must match payload case_id")
        return self


class PolicyReviewBundle(BaseModel):
    case_id: str = Field(min_length=1)
    action_type: ActionType
    order_id: str = Field(min_length=1)
    facts: list[SourceFact] = Field(min_length=1)
    retrieved_policy: list[PolicySearchHit] = Field(min_length=1)
    decision: EligibilityDecision

    @model_validator(mode="after")
    def validate_grounded_decision(self) -> PolicyReviewBundle:
        if self.decision.action_type is not self.action_type:
            raise ValueError("policy decision action_type must match the review action_type")
        fact_ids = [fact.fact_id for fact in self.facts]
        fact_fields = [fact.field for fact in self.facts]
        if len(fact_ids) != len(set(fact_ids)) or len(fact_fields) != len(set(fact_fields)):
            raise ValueError("policy review facts must have unique IDs and fields")
        cited_fact_ids = {
            *self.decision.conclusion.fact_ids,
            *(fact_id for check in self.decision.checks for fact_id in check.fact_ids),
        }
        if cited_fact_ids - set(fact_ids):
            raise ValueError("policy decision cites facts that are absent from the handoff")
        retrieved_clause_ids = {hit.clause.clause_id for hit in self.retrieved_policy}
        cited_clause_ids = {
            *self.decision.conclusion.policy_clause_ids,
            *(clause_id for check in self.decision.checks for clause_id in check.policy_clause_ids),
        }
        if cited_clause_ids - retrieved_clause_ids:
            raise ValueError("policy decision cites clauses that were not retrieved")
        return self


class PolicyToPlannerHandoff(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    handoff_type: Literal["policy_decision"] = "policy_decision"
    handoff_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    sender: Literal[AgentRole.POLICY_SPECIALIST] = AgentRole.POLICY_SPECIALIST
    recipient: Literal[AgentRole.PLANNER] = AgentRole.PLANNER
    payload: PolicyReviewBundle
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_case_identity(self) -> PolicyToPlannerHandoff:
        if self.case_id != self.payload.case_id:
            raise ValueError("handoff case_id must match payload case_id")
        return self


class CollaborationReviewRequest(BaseModel):
    analysis: OrderSpecialistRequest
    order_snapshot: dict[str, Any]
    product_snapshots: dict[str, dict[str, Any]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_order_snapshot(self) -> CollaborationReviewRequest:
        if str(self.order_snapshot.get("order_id") or "") != self.analysis.order_id:
            raise ValueError("order snapshot must match the requested order_id")
        return self


class SpecialistCollaborationResult(BaseModel):
    order_handoff: OrderToPolicyHandoff
    policy_handoff: PolicyToPlannerHandoff

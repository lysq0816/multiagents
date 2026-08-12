"""Typed state shared by agents and deterministic executors."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class Intent(StrEnum):
    ORDER_LOOKUP = "order_lookup"
    CANCEL_ORDER = "cancel_order"
    RETURN_ITEMS = "return_items"
    EXCHANGE_ITEMS = "exchange_items"
    RESHIP_ITEMS = "reship_items"


class ActionType(StrEnum):
    READ_USER = "read_user"
    READ_ORDER = "read_order"
    READ_PRODUCT = "read_product"
    CANCEL_ORDER = "cancel_order"
    CREATE_RETURN = "create_return"
    EXCHANGE_ITEMS = "exchange_items"
    RESHIP_ITEMS = "reship_items"

    @property
    def is_consequential(self) -> bool:
        return self in {
            ActionType.CANCEL_ORDER,
            ActionType.CREATE_RETURN,
            ActionType.EXCHANGE_ITEMS,
            ActionType.RESHIP_ITEMS,
        }


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RouteKind(StrEnum):
    NEEDS_CLARIFICATION = "needs_clarification"
    SINGLE_AGENT = "single_agent"
    MULTI_AGENT = "multi_agent"


class AgentRole(StrEnum):
    CUSTOMER_SERVICE = "customer_service"
    ORDER_SPECIALIST = "order_specialist"
    POLICY_SPECIALIST = "policy_specialist"
    INVENTORY_SPECIALIST = "inventory_specialist"
    PLANNER = "planner"
    AUDITOR = "auditor"


class ApprovalStatus(StrEnum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    APPROVED = "approved"
    EDITED = "edited"
    REJECTED = "rejected"


class EvidenceSource(StrEnum):
    USER = "user"
    TOOL = "tool"
    POLICY = "policy"


class Evidence(BaseModel):
    claim: str = Field(min_length=1)
    source: EvidenceSource
    source_id: str = Field(min_length=1)
    record_id: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class ProposedAction(BaseModel):
    action_type: ActionType
    order_id: str | None = None
    item_ids: list[str] = Field(default_factory=list)
    arguments: dict[str, Any] = Field(default_factory=dict)

    @property
    def requires_approval(self) -> bool:
        return self.action_type.is_consequential


class AuditEvent(BaseModel):
    event_type: str = Field(min_length=1)
    actor: str = Field(min_length=1)
    detail: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TicketIntake(BaseModel):
    ticket_id: str = Field(min_length=1)
    user_message: str = Field(min_length=1)
    intents: list[Intent] = Field(default_factory=list)
    order_ids: list[str] = Field(default_factory=list)
    requested_actions: list[ActionType] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    has_policy_conflict: bool = False
    requires_money_movement: bool = False
    requires_inventory_movement: bool = False
    user_confirmed: bool = False

    @field_validator("intents", "requested_actions", "order_ids")
    @classmethod
    def remove_duplicates(cls, values: list[Any]) -> list[Any]:
        return list(dict.fromkeys(values))


class RoutingDecision(BaseModel):
    route: RouteKind
    risk_level: RiskLevel
    reasons: list[str] = Field(default_factory=list)
    specialists: list[AgentRole] = Field(default_factory=list)
    approval_required: bool = False
    can_execute_now: bool = False


class CaseState(BaseModel):
    ticket_id: str = Field(min_length=1)
    user_id: str | None = None
    intents: list[Intent] = Field(default_factory=list)
    verified_facts: list[Evidence] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    order_snapshot: dict[str, Any] = Field(default_factory=dict)
    policy_evidence: list[Evidence] = Field(default_factory=list)
    candidate_actions: list[ProposedAction] = Field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.LOW
    approval_status: ApprovalStatus = ApprovalStatus.NOT_REQUIRED
    tool_results: list[dict[str, Any]] = Field(default_factory=list)
    audit_trail: list[AuditEvent] = Field(default_factory=list)

    @property
    def has_pending_consequential_actions(self) -> bool:
        return any(action.requires_approval for action in self.candidate_actions)

    @property
    def can_execute_consequential_actions(self) -> bool:
        if not self.has_pending_consequential_actions:
            return True
        return self.approval_status in {ApprovalStatus.APPROVED, ApprovalStatus.EDITED}

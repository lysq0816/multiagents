"""Typed policy clauses, source facts, and grounded eligibility decisions."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from after_sales_agents.domain.models import ActionType, Intent


class PolicyClause(BaseModel):
    clause_id: str = Field(pattern=r"^retail\.[a-z0-9_.]+$")
    title: str = Field(min_length=1)
    text: str = Field(min_length=1)
    source_section: str = Field(min_length=1)
    applies_to_intents: list[Intent] = Field(default_factory=list)
    applies_to_actions: list[ActionType] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class PolicyCatalog(BaseModel):
    catalog_id: str = Field(min_length=1)
    benchmark_version: str = Field(min_length=1)
    domain: str = Field(pattern=r"^retail$")
    source_path: str = Field(min_length=1)
    clauses: list[PolicyClause] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_clause_ids(self) -> PolicyCatalog:
        clause_ids = [clause.clause_id for clause in self.clauses]
        if len(clause_ids) != len(set(clause_ids)):
            raise ValueError("policy clause IDs must be unique")
        return self


class PolicySearchRequest(BaseModel):
    query: str = ""
    intents: list[Intent] = Field(default_factory=list)
    actions: list[ActionType] = Field(default_factory=list)
    top_k: int = Field(default=5, ge=1, le=20)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def require_search_signal(self) -> PolicySearchRequest:
        if not self.query and not self.intents and not self.actions:
            raise ValueError("provide a query, intent, or action for policy search")
        return self


class PolicySearchHit(BaseModel):
    score: float = Field(gt=0)
    match_reasons: list[str] = Field(min_length=1)
    clause: PolicyClause


class FactSourceType(StrEnum):
    USER = "user"
    TOOL = "tool"
    AGENT = "agent"


class FactField(StrEnum):
    USER_AUTHENTICATED = "user.authenticated"
    ORDER_STATUS = "order.status"
    ACTION_DETAILS_PRESENTED = "action.details_presented"
    USER_CONFIRMED = "user.confirmed"
    ORDER_ID_CONFIRMED = "order.id_confirmed"
    CANCEL_REASON = "cancel.reason"
    ITEM_IDS = "request.item_ids"
    TARGET_ITEM_IDS = "exchange.target_item_ids"
    PAYMENT_METHOD_ID = "payment.method_id"
    PAYMENT_METHOD_TYPE = "payment.method_type"
    PAYMENT_METHOD_EXISTS = "payment.method_exists"
    PAYMENT_METHOD_IS_ORIGINAL = "payment.method_is_original"
    TARGET_ITEMS_AVAILABLE = "exchange.targets_available"
    TARGET_ITEMS_SAME_PRODUCT = "exchange.targets_same_product"
    TARGET_ITEMS_DIFFERENT_OPTION = "exchange.targets_different_option"
    PRICE_DIFFERENCE = "exchange.price_difference"
    GIFT_CARD_BALANCE = "payment.gift_card_balance"


class SourceFact(BaseModel):
    fact_id: str = Field(min_length=1)
    field: FactField
    value: Any
    subject_id: str = Field(min_length=1)
    source_type: FactSourceType
    source_id: str = Field(min_length=1)
    derived_from_source_ids: list[str] = Field(default_factory=list)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EligibilityRequest(BaseModel):
    action_type: ActionType
    facts: list[SourceFact] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_supported_action_and_unique_facts(self) -> EligibilityRequest:
        supported = {
            ActionType.CANCEL_ORDER,
            ActionType.CREATE_RETURN,
            ActionType.EXCHANGE_ITEMS,
        }
        if self.action_type not in supported:
            raise ValueError("eligibility is implemented only for cancel, return, and exchange")
        fact_ids = [fact.fact_id for fact in self.facts]
        if len(fact_ids) != len(set(fact_ids)):
            raise ValueError("fact IDs must be unique")
        fields = [fact.field for fact in self.facts]
        if len(fields) != len(set(fields)):
            raise ValueError("each fact field may appear only once in an eligibility request")
        return self


class RequirementStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    MISSING = "missing"


class RequirementCheck(BaseModel):
    requirement_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    status: RequirementStatus
    fact_ids: list[str] = Field(default_factory=list)
    policy_clause_ids: list[str] = Field(min_length=1)


class EligibilityStatus(StrEnum):
    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    INSUFFICIENT_FACTS = "insufficient_facts"


class GroundedConclusion(BaseModel):
    statement: str = Field(min_length=1)
    fact_ids: list[str] = Field(default_factory=list)
    policy_clause_ids: list[str] = Field(min_length=1)


class EligibilityDecision(BaseModel):
    action_type: ActionType
    status: EligibilityStatus
    checks: list[RequirementCheck] = Field(min_length=1)
    missing_fact_fields: list[FactField] = Field(default_factory=list)
    conclusion: GroundedConclusion

    @model_validator(mode="after")
    def validate_status_and_citations(self) -> EligibilityDecision:
        statuses = {check.status for check in self.checks}
        if self.status is EligibilityStatus.ELIGIBLE and statuses != {RequirementStatus.PASSED}:
            raise ValueError("eligible decisions require every check to pass")
        if self.status is EligibilityStatus.INELIGIBLE and RequirementStatus.FAILED not in statuses:
            raise ValueError("ineligible decisions require at least one failed check")
        if (
            self.status is EligibilityStatus.INSUFFICIENT_FACTS
            and RequirementStatus.MISSING not in statuses
        ):
            raise ValueError("insufficient decisions require at least one missing check")
        if self.status is not EligibilityStatus.INSUFFICIENT_FACTS and not self.conclusion.fact_ids:
            raise ValueError("eligibility judgments require cited facts")
        return self


class BusinessCommitment(BaseModel):
    """A promise that cannot exist without both fact and policy citations."""

    statement: str = Field(min_length=1)
    fact_ids: list[str] = Field(min_length=1)
    policy_clause_ids: list[str] = Field(min_length=1)

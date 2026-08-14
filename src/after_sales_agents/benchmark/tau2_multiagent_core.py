"""Pure project-side models and routing helpers for the tau2 multi-agent runtime."""

from __future__ import annotations

import json
import re

from pydantic import BaseModel, Field, field_validator

from after_sales_agents.domain.models import (
    ActionType,
    AgentRole,
    Intent,
    RiskLevel,
    RouteKind,
    RoutingDecision,
    TicketIntake,
)
from after_sales_agents.domain.routing import DifficultyRouter

WRITE_TOOL_NAMES = frozenset(
    {
        "cancel_pending_order",
        "exchange_delivered_order_items",
        "modify_pending_order_address",
        "modify_pending_order_items",
        "modify_pending_order_payment",
        "modify_user_address",
        "return_delivered_order_items",
    }
)

_ORDER_ID_PATTERN = re.compile(r"\bW\d{7}\b", re.IGNORECASE)
_MULTI_AGENT_TERMS = (
    "exchange",
    "return",
    "replace",
    "swap",
    "different color",
    "different size",
    "change the item",
    "modify the item",
)
_AFFIRMATIVE_PATTERN = re.compile(
    r"^\s*(yes|yep|yeah|correct|confirmed?|please (do|proceed)|go ahead|do it|that is right)\b",
    re.IGNORECASE,
)
_RAW_TOOL_MARKUP_PATTERN = re.compile(
    r"(?:DSML.{0,80}tool_calls?|<\s*tool_calls?|<\s*function_calls?)",
    re.IGNORECASE | re.DOTALL,
)
_EXECUTION_CLAIM_PATTERN = re.compile(
    r"\b(?:i(?:'ve| have)|we(?:'ve| have))\s+(?:already\s+)?"
    r"(?:submitted|processed|completed|cancelled|canceled|exchanged|returned|updated|modified)\b"
    r"|\b(?:your|the)\s+(?:[a-z]+\s+){0,6}"
    r"(?:has been|is now|was successfully)\s+"
    r"(?:submitted|processed|completed|cancelled|canceled|exchanged|returned|updated|modified)\b",
    re.IGNORECASE,
)


class ConstraintLedger(BaseModel):
    """Structured handoff from the order/constraint specialist to the planner."""

    goal_summary: str = ""
    order_ids: list[str] = Field(default_factory=list)
    requested_actions: list[str] = Field(default_factory=list)
    item_constraints: list[str] = Field(default_factory=list)
    numeric_constraints: list[str] = Field(default_factory=list)
    conditional_branches: list[str] = Field(default_factory=list)
    confirmed_actions: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    prohibited_extra_actions: list[str] = Field(default_factory=list)


class PolicyReview(BaseModel):
    """Structured handoff from the policy specialist to the independent auditor."""

    candidate_allowed: bool
    confirmation_required: bool
    confirmation_present: bool
    missing_information: list[str] = Field(default_factory=list)
    violated_rules: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)
    repair_instruction: str = ""

    @field_validator("risk_notes", mode="before")
    @classmethod
    def _normalize_risk_notes(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, str):
            return [value] if value.strip() else []
        return value

    @field_validator("repair_instruction", mode="before")
    @classmethod
    def _normalize_repair_instruction(cls, value: object) -> object:
        return "" if value is None else value


class AuditDecision(BaseModel):
    """Independent audit result for one proposed consequential tool call."""

    approved: bool
    issues: list[str] = Field(default_factory=list)
    repair_instruction: str = ""

    @field_validator("repair_instruction", mode="before")
    @classmethod
    def _normalize_repair_instruction(cls, value: object) -> object:
        return "" if value is None else value


def route_tau2_message(case_id: str, user_text: str) -> RoutingDecision:
    """Translate a user turn into the existing deterministic difficulty router."""

    normalized = user_text.lower()
    intents: list[Intent] = []
    actions: list[ActionType] = []
    if "cancel" in normalized:
        intents.append(Intent.CANCEL_ORDER)
        actions.append(ActionType.CANCEL_ORDER)
    if "return" in normalized or "refund" in normalized:
        intents.append(Intent.RETURN_ITEMS)
        actions.append(ActionType.CREATE_RETURN)
    if "exchange" in normalized or "swap" in normalized:
        intents.append(Intent.EXCHANGE_ITEMS)
        actions.append(ActionType.EXCHANGE_ITEMS)
    if not intents and any(term in normalized for term in ("order", "purchase")):
        intents.append(Intent.ORDER_LOOKUP)

    inventory_movement = any(term in normalized for term in _MULTI_AGENT_TERMS)
    money_movement = any(
        term in normalized
        for term in ("cancel", "refund", "return", "exchange", "payment", "price")
    )
    ticket = TicketIntake(
        ticket_id=case_id,
        user_message=user_text,
        intents=intents,
        order_ids=[match.upper() for match in _ORDER_ID_PATTERN.findall(user_text)],
        requested_actions=actions,
        requires_money_movement=money_movement,
        requires_inventory_movement=inventory_movement,
        user_confirmed=is_explicit_confirmation(user_text),
    )
    decision = DifficultyRouter().route(ticket)

    generic_multi_agent = (inventory_movement and money_movement) or len(ticket.order_ids) > 1
    if generic_multi_agent and decision.route is not RouteKind.MULTI_AGENT:
        reasons = [*decision.reasons, "tau2_complex_write"]
        return RoutingDecision(
            route=RouteKind.MULTI_AGENT,
            risk_level=RiskLevel.HIGH,
            reasons=list(dict.fromkeys(reasons)),
            specialists=[
                AgentRole.ORDER_SPECIALIST,
                AgentRole.POLICY_SPECIALIST,
                AgentRole.PLANNER,
                AgentRole.AUDITOR,
            ],
            approval_required=True,
            can_execute_now=ticket.user_confirmed,
        )
    return decision


def is_explicit_confirmation(user_text: str) -> bool:
    """Recognize a direct confirmation for the deterministic audit fallback."""

    normalized = user_text.strip()
    if re.match(r"^\s*(no|nope|not yet|do not|don't)\b", normalized, re.IGNORECASE):
        return False
    return bool(_AFFIRMATIVE_PATTERN.search(normalized))


def is_write_tool(tool_name: str) -> bool:
    return tool_name in WRITE_TOOL_NAMES


def contains_raw_tool_markup(content: str | None) -> bool:
    """Detect provider tool syntax that was returned as user-visible text."""

    return bool(content and _RAW_TOOL_MARKUP_PATTERN.search(content))


def contains_execution_claim(content: str | None) -> bool:
    """Detect a text claim that a database-changing action already happened."""

    return bool(content and _EXECUTION_CLAIM_PATTERN.search(content))


def is_review_approved(
    policy_review: PolicyReview | None,
    audit: AuditDecision,
) -> bool:
    """Require both reviewers and any mandatory confirmation to agree."""

    if not audit.approved:
        return False
    if policy_review is None or not policy_review.candidate_allowed:
        return False
    return not (policy_review.confirmation_required and not policy_review.confirmation_present)


def parse_structured_handoff[ModelT: BaseModel](
    content: str | None, model_type: type[ModelT]
) -> ModelT | None:
    """Parse a JSON handoff while tolerating an optional Markdown fence."""

    if not content or not content.strip():
        return None
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        return model_type.model_validate(json.loads(text))
    except (json.JSONDecodeError, ValueError, TypeError):
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            return model_type.model_validate(json.loads(text[start : end + 1]))
        except (json.JSONDecodeError, ValueError, TypeError):
            return None

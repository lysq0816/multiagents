"""A genuine difficulty-routed multi-agent implementation of the tau2 Agent protocol."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from pydantic import BaseModel, Field
from tau2.agent.base.llm_config import LLMConfigMixin
from tau2.agent.base_agent import (
    HalfDuplexAgent,
    ValidAgentInputMessage,
    is_valid_agent_history_message,
)
from tau2.data_model.message import (
    APICompatibleMessage,
    AssistantMessage,
    Message,
    MultiToolMessage,
    SystemMessage,
    UserMessage,
)
from tau2.environment.tool import Tool
from tau2.utils.llm_utils import generate

from after_sales_agents.benchmark.tau2_multiagent_core import (
    AuditDecision,
    ConstraintLedger,
    PolicyReview,
    is_review_approved,
    is_write_tool,
    parse_structured_handoff,
    route_tau2_message,
)
from after_sales_agents.domain.models import RouteKind

AGENT_NAME = "after_sales_multiagent"

COORDINATOR_INSTRUCTION = """
You are the customer-facing coordinator of a difficulty-routed retail support team.
Only your response is visible to the customer or executable by the environment.

In each turn, either send one user-facing message or call exactly one tool, never both.
Follow the official policy exactly. Authenticate before disclosing account information.
Before every database-changing action, state all exact details and obtain explicit confirmation.
Preserve every order ID, item ID, numeric attribute, conditional branch, and cross-order relation.
Never perform a database-changing action that the customer did not request. In particular,
do not replace an entire order payment method when the customer only selected a method for an
item price difference. Use the calculate tool for monetary arithmetic.

Specialist handoffs are structured evidence, not permission to ignore the policy. Do not mention
internal agents, routing, ledgers, or audits to the customer.
""".strip()

CONSTRAINT_SPECIALIST_INSTRUCTION = """
You are the order and constraint specialist. Convert the conversation into a compact structured
ledger. Preserve exact identifiers, quantities, sizes, colors, amounts, conditions, cross-order
references, requested writes, confirmations, and actions the customer did not request.
Do not solve the task and do not call tools. Return one JSON object using exactly these keys:
goal_summary, order_ids, requested_actions, item_constraints, numeric_constraints,
conditional_branches, confirmed_actions, unresolved_questions, prohibited_extra_actions.
Every list value must be an array of strings. Return no prose outside JSON.
""".strip()

POLICY_SPECIALIST_INSTRUCTION = """
You are the policy specialist. Review one proposed consequential tool call against the complete
retail policy, the conversation, and the constraint ledger. Check authentication, order status,
exact arguments, required payment details, confirmation, and whether the action was requested.
Return one JSON object using exactly these keys: candidate_allowed, confirmation_required,
confirmation_present, missing_information, violated_rules, risk_notes, repair_instruction.
The first three values must be booleans; the next three must be arrays of strings; and
repair_instruction must be a string, using an empty string rather than null.
Return no prose outside JSON.
""".strip()

AUDITOR_INSTRUCTION = """
You are an independent auditor. Decide whether the exact proposed tool call may execute now.
Reject extra writes, lost numeric or relational constraints, wrong order/item bindings, missing
authentication, missing explicit confirmation, or any conflict with the policy specialist.
Return one JSON object using exactly these keys: approved, issues, repair_instruction.
approved must be a boolean, issues must be an array of strings, and repair_instruction must
be a string, using an empty string rather than null.
Return no prose outside JSON.
""".strip()


class RoutedMultiAgentState(BaseModel):
    """Conversation state plus auditable internal handoffs."""

    case_id: str
    messages: list[APICompatibleMessage] = Field(default_factory=list)
    ledger: ConstraintLedger | None = None
    multi_agent_active: bool = False
    route_history: list[dict[str, Any]] = Field(default_factory=list)
    role_call_counts: dict[str, int] = Field(default_factory=dict)


class RoutedTau2MultiAgent(
    LLMConfigMixin,
    HalfDuplexAgent[RoutedMultiAgentState],
):
    """Coordinator, specialist and auditor roles behind one official tau2 participant."""

    def __init__(
        self,
        tools: list[Tool],
        domain_policy: str,
        llm: str,
        llm_args: dict[str, Any] | None = None,
        case_id: str = "tau2-case",
    ) -> None:
        super().__init__(
            tools=tools,
            domain_policy=domain_policy,
            llm=llm,
            llm_args=llm_args,
        )
        self.case_id = case_id

    def get_init_state(
        self,
        message_history: list[Message] | None = None,
    ) -> RoutedMultiAgentState:
        history = message_history or []
        assert all(is_valid_agent_history_message(message) for message in history), (
            "Message history must contain only valid agent-side tau2 messages."
        )
        return RoutedMultiAgentState(case_id=self.case_id, messages=history)

    def generate_next_message(
        self,
        message: ValidAgentInputMessage,
        state: RoutedMultiAgentState,
    ) -> tuple[AssistantMessage, RoutedMultiAgentState]:
        llm_calls: list[AssistantMessage] = []
        turn_trace: dict[str, Any] = {
            "case_id": state.case_id,
            "consulted_roles": [],
            "policy_reviews": [],
            "audits": [],
        }

        if isinstance(message, MultiToolMessage):
            state.messages.extend(message.tool_messages)
        else:
            if isinstance(message, UserMessage) and message.is_audio:
                raise ValueError("RoutedTau2MultiAgent supports text user messages only")
            state.messages.append(message)

        if isinstance(message, UserMessage) and not message.is_tool_call():
            self._route_user_turn(message, state, llm_calls, turn_trace)

        candidate = self._coordinator_generate(state, llm_calls, turn_trace)
        candidate = self._normalize_candidate(candidate)

        if self._candidate_is_consequential(candidate):
            candidate = self._review_and_repair(
                candidate,
                state,
                llm_calls,
                turn_trace,
            )

        self._attach_accounting_and_trace(candidate, llm_calls, state, turn_trace)
        state.messages.append(candidate)
        return candidate, state

    def _route_user_turn(
        self,
        message: UserMessage,
        state: RoutedMultiAgentState,
        llm_calls: list[AssistantMessage],
        turn_trace: dict[str, Any],
    ) -> None:
        text = message.content or ""
        decision = route_tau2_message(state.case_id, text)
        route_record = decision.model_dump(mode="json")
        state.route_history.append(route_record)
        turn_trace["route"] = route_record
        should_consult = decision.route is RouteKind.MULTI_AGENT or state.multi_agent_active
        if not should_consult:
            return

        state.multi_agent_active = True
        handoff = self._structured_call(
            role="order_constraint_specialist",
            instruction=CONSTRAINT_SPECIALIST_INSTRUCTION,
            payload={
                "previous_ledger": (state.ledger.model_dump(mode="json") if state.ledger else None),
                "conversation": self._compact_transcript(state.messages),
            },
            model_type=ConstraintLedger,
            state=state,
            llm_calls=llm_calls,
            turn_trace=turn_trace,
        )
        if handoff is not None:
            state.ledger = handoff
        turn_trace["constraint_ledger"] = (
            state.ledger.model_dump(mode="json") if state.ledger else None
        )

    def _coordinator_generate(
        self,
        state: RoutedMultiAgentState,
        llm_calls: list[AssistantMessage],
        turn_trace: dict[str, Any],
        audit_feedback: str | None = None,
        allow_tools: bool = True,
    ) -> AssistantMessage:
        handoff = {
            "route": turn_trace.get("route"),
            "constraint_ledger": (state.ledger.model_dump(mode="json") if state.ledger else None),
            "audit_feedback": audit_feedback,
        }
        system_prompt = (
            f"{COORDINATOR_INSTRUCTION}\n\n<policy>\n{self.domain_policy}\n</policy>"
            f"\n\n<specialist_handoff>\n{json.dumps(handoff, ensure_ascii=False)}"
            "\n</specialist_handoff>"
        )
        generated = generate(
            model=self.llm,
            tools=self.tools if allow_tools else None,
            messages=[SystemMessage(role="system", content=system_prompt), *state.messages],
            call_name="after_sales_coordinator",
            **self.llm_args,
        )
        if not isinstance(generated, AssistantMessage):
            raise TypeError("Coordinator must return an AssistantMessage")
        self._record_call("coordinator", generated, state, llm_calls, turn_trace)
        return generated

    def _review_and_repair(
        self,
        candidate: AssistantMessage,
        state: RoutedMultiAgentState,
        llm_calls: list[AssistantMessage],
        turn_trace: dict[str, Any],
    ) -> AssistantMessage:
        policy_review, audit = self._audit_candidate(
            candidate,
            state,
            llm_calls,
            turn_trace,
        )
        if self._is_approved(policy_review, audit):
            return candidate

        feedback = self._repair_instruction(policy_review, audit)
        repaired = self._normalize_candidate(
            self._coordinator_generate(
                state,
                llm_calls,
                turn_trace,
                audit_feedback=feedback,
            )
        )
        if not self._candidate_is_consequential(repaired):
            turn_trace["repair_outcome"] = "non_consequential_response"
            return repaired

        second_policy, second_audit = self._audit_candidate(
            repaired,
            state,
            llm_calls,
            turn_trace,
        )
        if self._is_approved(second_policy, second_audit):
            turn_trace["repair_outcome"] = "approved_after_repair"
            return repaired

        final_feedback = self._repair_instruction(second_policy, second_audit)
        safe_response = self._normalize_candidate(
            self._coordinator_generate(
                state,
                llm_calls,
                turn_trace,
                audit_feedback=(
                    "Do not call any tool. Ask the customer for the missing confirmation or "
                    f"information needed to resolve this audit: {final_feedback}"
                ),
                allow_tools=False,
            )
        )
        turn_trace["repair_outcome"] = "blocked_pending_user_clarification"
        return safe_response

    def _audit_candidate(
        self,
        candidate: AssistantMessage,
        state: RoutedMultiAgentState,
        llm_calls: list[AssistantMessage],
        turn_trace: dict[str, Any],
    ) -> tuple[PolicyReview | None, AuditDecision]:
        shared_payload = {
            "policy": self.domain_policy,
            "conversation": self._compact_transcript(state.messages),
            "constraint_ledger": (state.ledger.model_dump(mode="json") if state.ledger else None),
            "candidate": self._compact_candidate(candidate),
        }
        policy_review = self._structured_call(
            role="policy_specialist",
            instruction=POLICY_SPECIALIST_INSTRUCTION,
            payload=shared_payload,
            model_type=PolicyReview,
            state=state,
            llm_calls=llm_calls,
            turn_trace=turn_trace,
        )
        turn_trace["policy_reviews"].append(
            policy_review.model_dump(mode="json") if policy_review else None
        )

        audit = self._structured_call(
            role="independent_auditor",
            instruction=AUDITOR_INSTRUCTION,
            payload={
                **shared_payload,
                "policy_review": (policy_review.model_dump(mode="json") if policy_review else None),
            },
            model_type=AuditDecision,
            state=state,
            llm_calls=llm_calls,
            turn_trace=turn_trace,
        )
        if audit is None:
            audit = AuditDecision(
                approved=False,
                issues=["independent_auditor_invalid_handoff"],
                repair_instruction=(
                    "Do not execute the write. Restate the proposed action and obtain "
                    "a valid independent audit before trying again."
                ),
            )
        if policy_review is not None and not policy_review.candidate_allowed and audit.approved:
            audit = audit.model_copy(
                update={
                    "approved": False,
                    "issues": [*audit.issues, "policy_specialist_rejected_candidate"],
                    "repair_instruction": (
                        policy_review.repair_instruction or audit.repair_instruction
                    ),
                }
            )
        turn_trace["audits"].append(audit.model_dump(mode="json"))
        return policy_review, audit

    def _structured_call(
        self,
        *,
        role: str,
        instruction: str,
        payload: dict[str, Any],
        model_type: type[BaseModel],
        state: RoutedMultiAgentState,
        llm_calls: list[AssistantMessage],
        turn_trace: dict[str, Any],
    ) -> BaseModel | None:
        structured_args = dict(self.llm_args)
        structured_args["response_format"] = {"type": "json_object"}
        if self.llm.lower().startswith("deepseek/"):
            structured_args.pop("thinking", None)
            structured_args.pop("reasoning_effort", None)
            extra_body = dict(structured_args.get("extra_body") or {})
            extra_body["thinking"] = {"type": "disabled"}
            structured_args["extra_body"] = extra_body
            turn_trace["structured_call_thinking"] = "disabled"
        else:
            turn_trace["structured_call_thinking"] = "provider_default"
        generated = generate(
            model=self.llm,
            messages=[
                SystemMessage(role="system", content=instruction),
                UserMessage(
                    role="user",
                    content=json.dumps(payload, ensure_ascii=False, default=str),
                ),
            ],
            call_name=f"after_sales_{role}",
            **structured_args,
        )
        if not isinstance(generated, AssistantMessage):
            return None
        self._record_call(role, generated, state, llm_calls, turn_trace)
        parsed = parse_structured_handoff(generated.content, model_type)
        if parsed is None:
            turn_trace.setdefault("invalid_handoffs", []).append(role)
        return parsed

    @staticmethod
    def _compact_transcript(messages: list[APICompatibleMessage]) -> list[dict[str, Any]]:
        allowed_fields = {"role", "content", "tool_calls", "id", "requestor", "error"}
        compact = []
        for message in messages[-24:]:
            payload = message.model_dump(mode="json", exclude_none=True)
            compact.append({key: value for key, value in payload.items() if key in allowed_fields})
        return compact

    @staticmethod
    def _compact_candidate(message: AssistantMessage) -> dict[str, Any]:
        return {
            "role": message.role,
            "content": message.content,
            "tool_calls": (
                [tool_call.model_dump(mode="json") for tool_call in message.tool_calls]
                if message.tool_calls
                else None
            ),
        }

    @staticmethod
    def _normalize_candidate(message: AssistantMessage) -> AssistantMessage:
        if message.tool_calls:
            message.content = None
            message.tool_calls = message.tool_calls[:1]
        if not message.has_text_content() and not message.is_tool_call():
            raise ValueError("Coordinator returned an empty response")
        return message

    @staticmethod
    def _candidate_is_consequential(message: AssistantMessage) -> bool:
        return bool(message.tool_calls and is_write_tool(message.tool_calls[0].name))

    @staticmethod
    def _is_approved(
        policy_review: PolicyReview | None,
        audit: AuditDecision,
    ) -> bool:
        return is_review_approved(policy_review, audit)

    @staticmethod
    def _repair_instruction(
        policy_review: PolicyReview | None,
        audit: AuditDecision,
    ) -> str:
        instructions = []
        if policy_review is not None and policy_review.repair_instruction:
            instructions.append(policy_review.repair_instruction)
        if audit.repair_instruction:
            instructions.append(audit.repair_instruction)
        if not instructions:
            instructions.extend(audit.issues)
        return " ".join(instructions) or "Ask for explicit confirmation before the write."

    @staticmethod
    def _record_call(
        role: str,
        message: AssistantMessage,
        state: RoutedMultiAgentState,
        llm_calls: list[AssistantMessage],
        turn_trace: dict[str, Any],
    ) -> None:
        llm_calls.append(message)
        state.role_call_counts[role] = state.role_call_counts.get(role, 0) + 1
        turn_trace["consulted_roles"].append(role)

    def _attach_accounting_and_trace(
        self,
        output: AssistantMessage,
        llm_calls: list[AssistantMessage],
        state: RoutedMultiAgentState,
        turn_trace: dict[str, Any],
    ) -> None:
        costs = [
            call.cost
            for call in llm_calls
            if isinstance(call.cost, (int, float)) and not isinstance(call.cost, bool)
        ]
        missing_cost_calls = len(llm_calls) - len(costs)
        provider_cost_unmapped = (
            self.llm.lower() == "deepseek/deepseek-v4-flash"
            and bool(costs)
            and all(cost == 0 for cost in costs)
        )
        output.cost = (
            sum(costs) if costs and missing_cost_calls == 0 and not provider_cost_unmapped else None
        )
        usage: Counter[str] = Counter()
        missing_usage_calls = 0
        for call in llm_calls:
            if not isinstance(call.usage, dict):
                missing_usage_calls += 1
                continue
            usage.update(
                {
                    key: value
                    for key, value in call.usage.items()
                    if isinstance(value, (int, float)) and not isinstance(value, bool)
                }
            )
        output.usage = dict(usage) if usage else None
        generation_times = [
            call.generation_time_seconds
            for call in llm_calls
            if isinstance(call.generation_time_seconds, (int, float))
            and not isinstance(call.generation_time_seconds, bool)
        ]
        missing_generation_time_calls = len(llm_calls) - len(generation_times)
        output.generation_time_seconds = (
            sum(generation_times)
            if generation_times and missing_generation_time_calls == 0
            else None
        )
        raw_data = output.raw_data if isinstance(output.raw_data, dict) else {}
        turn_trace["accounting"] = {
            "internal_call_count": len(llm_calls),
            "cost_complete": missing_cost_calls == 0 and not provider_cost_unmapped,
            "missing_cost_call_count": missing_cost_calls,
            "cost_unavailable_reason": (
                "provider_model_unmapped" if provider_cost_unmapped else None
            ),
            "usage_complete": missing_usage_calls == 0,
            "missing_usage_call_count": missing_usage_calls,
            "generation_time_complete": missing_generation_time_calls == 0,
            "missing_generation_time_call_count": missing_generation_time_calls,
        }
        turn_trace["cumulative_role_call_counts"] = dict(state.role_call_counts)
        turn_trace["returned_tool"] = output.tool_calls[0].name if output.tool_calls else None
        raw_data["after_sales_multiagent_trace"] = turn_trace
        output.raw_data = raw_data


def create_after_sales_multiagent(tools, domain_policy, **kwargs):
    """Factory used by the official tau2 registry."""

    task = kwargs.get("task")
    case_id = f"tau2-retail:{getattr(task, 'id', 'unknown')}"
    return RoutedTau2MultiAgent(
        tools=tools,
        domain_policy=domain_policy,
        llm=kwargs.get("llm"),
        llm_args=kwargs.get("llm_args"),
        case_id=case_id,
    )


def register_after_sales_multiagent() -> str:
    """Register without modifying the external tau2 checkout."""

    from tau2.registry import registry

    if registry.get_agent_factory(AGENT_NAME) is None:
        registry.register_agent_factory(create_after_sales_multiagent, AGENT_NAME)
    return AGENT_NAME

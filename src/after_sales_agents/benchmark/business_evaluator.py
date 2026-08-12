"""Conservative local business compatibility checks for τ2 result files.

This evaluator does not replace or modify the official τ2 reward. It handles two
narrow equivalences: a reordered additive calculator expression, and either Retail-
policy cancellation reason when the task scenario did not choose one.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

BUSINESS_EVALUATION_PROFILE = "retail_action_compatibility_v2"
ALLOWED_CANCEL_REASONS = frozenset({"no longer needed", "ordered by mistake"})
CANCEL_TOOL_NAME = "cancel_pending_order"


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _tool_arguments(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return _as_mapping(parsed)
    return {}


def _scenario_cancel_reasons(task: Mapping[str, Any]) -> set[str]:
    scenario = _as_mapping(task.get("user_scenario"))
    instructions = _as_mapping(scenario.get("instructions"))
    reason_for_call = str(instructions.get("reason_for_call") or "").lower()
    return {reason for reason in ALLOWED_CANCEL_REASONS if reason in reason_for_call}


def _expected_cancel_action(task: Mapping[str, Any]) -> Mapping[str, Any]:
    criteria = _as_mapping(task.get("evaluation_criteria"))
    actions = criteria.get("actions") or []
    matches = [action for action in actions if _as_mapping(action).get("name") == CANCEL_TOOL_NAME]
    if len(matches) != 1:
        raise ValueError("business compatibility evaluation requires one expected cancellation")
    return _as_mapping(matches[0])


def _find_tool_response(messages: list[Any], call_id: Any) -> Mapping[str, Any]:
    if not call_id:
        return {}
    for message in messages:
        candidate = _as_mapping(message)
        if candidate.get("role") == "tool" and candidate.get("id") == call_id:
            return candidate
    return {}


def _additive_terms(expression: str) -> tuple[Decimal, ...] | None:
    """Parse a plain addition while retaining its complete multiset of terms."""

    parts = expression.split("+")
    if len(parts) < 2 or any(not part.strip() for part in parts):
        return None
    try:
        terms = tuple(Decimal(part.strip()) for part in parts)
    except InvalidOperation:
        return None
    if any(not term.is_finite() for term in terms):
        return None
    return tuple(sorted(terms))


def _response_decimal(response: Mapping[str, Any]) -> Decimal | None:
    if not response or response.get("error") is not False:
        return None
    content = response.get("content")
    try:
        decoded = json.loads(content) if isinstance(content, str) else content
        value = Decimal(str(decoded))
    except (InvalidOperation, json.JSONDecodeError, TypeError, ValueError):
        return None
    return value if value.is_finite() else None


def _compatible_calculation_call(
    action_check: Mapping[str, Any], messages: list[Any]
) -> Mapping[str, Any]:
    expected_action = _as_mapping(action_check.get("action"))
    expected_arguments = _tool_arguments(expected_action.get("arguments"))
    expected_expression = str(expected_arguments.get("expression") or "")
    expected_terms = _additive_terms(expected_expression)
    if expected_terms is None:
        return {}

    for message in messages:
        for tool_call in _as_mapping(message).get("tool_calls") or []:
            tool_call = _as_mapping(tool_call)
            if tool_call.get("name") != "calculate":
                continue
            actual_arguments = _tool_arguments(tool_call.get("arguments"))
            actual_expression = str(actual_arguments.get("expression") or "")
            actual_terms = _additive_terms(actual_expression)
            if actual_terms != expected_terms:
                continue
            response = _find_tool_response(messages, tool_call.get("id"))
            expected_total = sum(expected_terms, start=Decimal(0))
            if _response_decimal(response) == expected_total:
                return tool_call
    return {}


def evaluate_business_compatibility(
    task: Mapping[str, Any], simulation: Mapping[str, Any]
) -> dict[str, Any]:
    """Return a local score while preserving the official reward as evidence."""

    expected_cancel = _expected_cancel_action(task)
    expected_arguments = _tool_arguments(expected_cancel.get("arguments"))
    expected_order_id = str(expected_arguments.get("order_id") or "")
    expected_reason = str(expected_arguments.get("reason") or "").strip().lower()

    criteria = _as_mapping(task.get("evaluation_criteria"))
    expected_non_cancel_count = sum(
        _as_mapping(action).get("name") != CANCEL_TOOL_NAME
        for action in criteria.get("actions") or []
    )
    messages = simulation.get("messages") or []
    reward_info = _as_mapping(simulation.get("reward_info"))
    action_checks = reward_info.get("action_checks") or []
    non_cancel_checks = [
        _as_mapping(check)
        for check in action_checks
        if _as_mapping(_as_mapping(check).get("action")).get("name") != CANCEL_TOOL_NAME
    ]
    compatible_calculation_call: Mapping[str, Any] = {}
    non_cancel_matches: list[bool] = []
    for check in non_cancel_checks:
        if check.get("action_match") is True:
            non_cancel_matches.append(True)
            continue
        action_name = _as_mapping(check.get("action")).get("name")
        if action_name == "calculate":
            compatible_calculation_call = _compatible_calculation_call(check, messages)
            non_cancel_matches.append(bool(compatible_calculation_call))
        else:
            non_cancel_matches.append(False)
    non_cancel_actions_match = len(non_cancel_checks) == expected_non_cancel_count and all(
        non_cancel_matches
    )

    cancel_calls: list[Mapping[str, Any]] = []
    for message in messages:
        for tool_call in _as_mapping(message).get("tool_calls") or []:
            tool_call = _as_mapping(tool_call)
            if tool_call.get("name") == CANCEL_TOOL_NAME:
                cancel_calls.append(tool_call)

    single_cancel_call = len(cancel_calls) == 1
    actual_call = cancel_calls[0] if single_cancel_call else {}
    actual_arguments = _tool_arguments(actual_call.get("arguments"))
    actual_order_id = str(actual_arguments.get("order_id") or "")
    actual_reason = str(actual_arguments.get("reason") or "").strip().lower()

    explicit_reasons = _scenario_cancel_reasons(task)
    accepted_reasons = explicit_reasons or set(ALLOWED_CANCEL_REASONS)
    cancel_order_matches = single_cancel_call and actual_order_id == expected_order_id
    cancel_reason_allowed = single_cancel_call and actual_reason in accepted_reasons

    actual_call_id = actual_call.get("id")
    matching_response = _find_tool_response(messages, actual_call_id)

    response_content = _tool_arguments(matching_response.get("content"))
    cancel_tool_succeeded = (
        bool(matching_response)
        and matching_response.get("error") is False
        and response_content.get("status") == "cancelled"
        and str(response_content.get("cancel_reason") or "").strip().lower() == actual_reason
    )

    expected_nl_count = len(criteria.get("nl_assertions") or [])
    nl_assertions = [_as_mapping(item) for item in reward_info.get("nl_assertions") or []]
    nl_assertions_met = len(nl_assertions) >= expected_nl_count and all(
        item.get("met") is True for item in nl_assertions
    )

    checks = {
        "non_cancel_actions_match": non_cancel_actions_match,
        "single_cancel_call": single_cancel_call,
        "cancel_order_matches": cancel_order_matches,
        "cancel_reason_allowed": cancel_reason_allowed,
        "cancel_tool_succeeded": cancel_tool_succeeded,
        "nl_assertions_met": nl_assertions_met,
    }
    business_reward = float(all(checks.values()))
    official_reward = float(reward_info.get("reward") or 0.0)
    compatibility_applied = (
        not explicit_reasons
        and actual_reason != expected_reason
        and actual_reason in ALLOWED_CANCEL_REASONS
    )
    calculation_compatibility_applied = bool(compatible_calculation_call)

    notes = [
        "The official τ2 reward is preserved and is not recalculated.",
        (
            "The local score accepts both Retail-policy cancellation reasons only when "
            "the scenario did not specify one."
        ),
    ]
    if compatibility_applied:
        notes.append("A policy-valid simulated-user reason differed from the single gold reason.")
    if calculation_compatibility_applied:
        notes.append(
            "The calculator used the complete gold addends in a different order and "
            "returned the correct total."
        )

    return {
        "evaluation_profile": BUSINESS_EVALUATION_PROFILE,
        "task_id": str(simulation.get("task_id") or task.get("id") or ""),
        "benchmark_reward": official_reward,
        "official_reward": official_reward,
        "business_reward": business_reward,
        "business_reward_is_diagnostic_only": True,
        "official_score_preserved": True,
        "reason_compatibility_applied": compatibility_applied,
        "calculation_compatibility_applied": calculation_compatibility_applied,
        "checks": checks,
        "evidence": {
            "expected_order_id": expected_order_id,
            "actual_order_id": actual_order_id or None,
            "gold_cancel_reason": expected_reason,
            "actual_cancel_reason": actual_reason or None,
            "scenario_explicit_cancel_reasons": sorted(explicit_reasons),
            "accepted_cancel_reasons": sorted(accepted_reasons),
            "compatible_calculation_expression": _tool_arguments(
                compatible_calculation_call.get("arguments")
            ).get("expression"),
        },
        "notes": notes,
    }

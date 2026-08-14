from after_sales_agents.benchmark.tau2_multiagent_core import (
    AuditDecision,
    ConstraintLedger,
    PolicyReview,
    is_explicit_confirmation,
    is_review_approved,
    is_write_tool,
    parse_structured_handoff,
    route_tau2_message,
)
from after_sales_agents.domain.models import AgentRole, RouteKind


def test_exchange_routes_to_real_specialists() -> None:
    decision = route_tau2_message(
        "case-1",
        "Please exchange item 123 in order W1234567 for a different size.",
    )

    assert decision.route is RouteKind.MULTI_AGENT
    assert AgentRole.ORDER_SPECIALIST in decision.specialists
    assert AgentRole.POLICY_SPECIALIST in decision.specialists
    assert AgentRole.AUDITOR in decision.specialists


def test_routine_lookup_stays_single_agent() -> None:
    decision = route_tau2_message("case-2", "What is the status of order W1234567?")

    assert decision.route is RouteKind.SINGLE_AGENT
    assert decision.specialists == [AgentRole.CUSTOMER_SERVICE]


def test_multiple_orders_force_multi_agent_routing() -> None:
    decision = route_tau2_message(
        "case-3",
        "Compare order W1234567 with order W7654321 before changing anything.",
    )

    assert decision.route is RouteKind.MULTI_AGENT
    assert "multiple_orders" in decision.reasons


def test_structured_handoff_accepts_json_fence_and_rejects_empty_output() -> None:
    parsed = parse_structured_handoff(
        """```json
        {"goal_summary":"exchange","order_ids":["W1234567"],
        "requested_actions":["exchange"],"item_constraints":[],
        "numeric_constraints":[],"conditional_branches":[],
        "confirmed_actions":[],"unresolved_questions":[],
        "prohibited_extra_actions":["change payment"]}
        ```""",
        ConstraintLedger,
    )

    assert parsed is not None
    assert parsed.order_ids == ["W1234567"]
    assert parse_structured_handoff("", AuditDecision) is None


def test_confirmation_fallback_is_explicit_and_write_tools_are_bounded() -> None:
    assert is_explicit_confirmation("Yes, please proceed with that exact change.") is True
    assert is_explicit_confirmation("No, do not do that yet.") is False
    assert is_write_tool("modify_pending_order_items") is True
    assert is_write_tool("get_order_details") is False
    assert is_write_tool("transfer_to_human_agents") is False


def test_review_never_approves_a_write_when_required_confirmation_is_missing() -> None:
    policy_review = PolicyReview(
        candidate_allowed=True,
        confirmation_required=True,
        confirmation_present=False,
    )
    mistaken_audit = AuditDecision(approved=True)

    assert is_review_approved(policy_review, mistaken_audit) is False
    assert is_review_approved(None, mistaken_audit) is False
    assert (
        is_review_approved(
            policy_review.model_copy(update={"candidate_allowed": False}),
            mistaken_audit,
        )
        is False
    )
    assert is_review_approved(policy_review, AuditDecision(approved=False)) is False

    confirmed_review = policy_review.model_copy(update={"confirmation_present": True})
    assert is_review_approved(confirmed_review, mistaken_audit) is True


def test_structured_reviews_accept_provider_string_lists_and_null_repairs() -> None:
    policy = parse_structured_handoff(
        """{
          "candidate_allowed": true,
          "confirmation_required": true,
          "confirmation_present": true,
          "missing_information": [],
          "violated_rules": [],
          "risk_notes": "order remains pending",
          "repair_instruction": null
        }""",
        PolicyReview,
    )
    audit = parse_structured_handoff(
        '{"approved":true,"issues":[],"repair_instruction":null}',
        AuditDecision,
    )

    assert policy is not None
    assert policy.risk_notes == ["order remains pending"]
    assert policy.repair_instruction == ""
    assert audit is not None
    assert audit.repair_instruction == ""
    assert (
        parse_structured_handoff(
            """{
              "candidate_allowed": true,
              "confirmation_required": true,
              "confirmation_present": true,
              "missing_information": "not an array",
              "violated_rules": [],
              "risk_notes": [],
              "repair_instruction": ""
            }""",
            PolicyReview,
        )
        is None
    )

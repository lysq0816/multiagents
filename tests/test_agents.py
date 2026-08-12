import pytest
from pydantic import ValidationError

from after_sales_agents.agents.models import (
    CollaborationReviewRequest,
    ExchangeTargetRequest,
    OrderSpecialistRequest,
    OrderToPolicyHandoff,
)
from after_sales_agents.agents.permissions import (
    SnapshotRetailTools,
    ToolName,
    ToolPermissionDenied,
    ToolPermissionGuard,
)
from after_sales_agents.agents.workflow import SpecialistWorkflow
from after_sales_agents.api import app
from after_sales_agents.domain.models import ActionType, AgentRole
from after_sales_agents.policy.models import (
    EligibilityStatus,
    FactField,
    FactSourceType,
    SourceFact,
)


def _fact(
    field: FactField,
    value: object,
    source_type: FactSourceType,
) -> SourceFact:
    return SourceFact(
        fact_id=f"fact:{field.value}",
        field=field,
        value=value,
        subject_id="#ORDER-1",
        source_type=source_type,
        source_id=f"source:{field.value}",
    )


def _common_facts(*, include_confirmation: bool = True) -> list[SourceFact]:
    facts = [
        _fact(FactField.USER_AUTHENTICATED, True, FactSourceType.TOOL),
        _fact(FactField.ACTION_DETAILS_PRESENTED, True, FactSourceType.AGENT),
    ]
    if include_confirmation:
        facts.append(_fact(FactField.USER_CONFIRMED, True, FactSourceType.USER))
    return facts


def _cancel_request(*, include_confirmation: bool = True) -> CollaborationReviewRequest:
    return CollaborationReviewRequest(
        analysis=OrderSpecialistRequest(
            case_id="case-cancel-1",
            action_type=ActionType.CANCEL_ORDER,
            order_id="#ORDER-1",
            provided_facts=[
                *_common_facts(include_confirmation=include_confirmation),
                _fact(FactField.ORDER_ID_CONFIRMED, True, FactSourceType.USER),
                _fact(
                    FactField.CANCEL_REASON,
                    "no longer needed",
                    FactSourceType.USER,
                ),
            ],
        ),
        order_snapshot={"order_id": "#ORDER-1", "status": "pending"},
    )


def test_specialists_have_no_write_tool_permissions() -> None:
    guard = ToolPermissionGuard()

    for role in (AgentRole.ORDER_SPECIALIST, AgentRole.POLICY_SPECIALIST):
        assert guard.allowed_tools(role)
        assert all(not tool.is_write for tool in guard.allowed_tools(role))


def test_order_specialist_is_blocked_from_cancellation_tool() -> None:
    tools = SnapshotRetailTools({"order_id": "#ORDER-1", "status": "pending"})

    with pytest.raises(ToolPermissionDenied, match="not allowed"):
        tools.call(
            AgentRole.ORDER_SPECIALIST,
            ToolName.CANCEL_PENDING_ORDER,
            {"order_id": "#ORDER-1"},
        )


def test_policy_specialist_is_blocked_from_order_reads() -> None:
    with pytest.raises(ToolPermissionDenied, match="not allowed"):
        ToolPermissionGuard().ensure_allowed(
            AgentRole.POLICY_SPECIALIST,
            ToolName.GET_ORDER_DETAILS,
        )


def test_cancel_workflow_uses_structured_handoffs_and_is_eligible() -> None:
    result = SpecialistWorkflow().review(_cancel_request())

    assert result.order_handoff.sender is AgentRole.ORDER_SPECIALIST
    assert result.order_handoff.recipient is AgentRole.POLICY_SPECIALIST
    assert result.order_handoff.payload.tool_calls[0].tool_name == "get_order_details"
    assert result.policy_handoff.sender is AgentRole.POLICY_SPECIALIST
    assert result.policy_handoff.recipient is AgentRole.PLANNER
    assert result.policy_handoff.payload.decision.status is EligibilityStatus.ELIGIBLE
    assert "retail.cancel.pending_only" in (
        result.policy_handoff.payload.decision.conclusion.policy_clause_ids
    )


def test_missing_user_confirmation_survives_handoff_as_missing_fact() -> None:
    result = SpecialistWorkflow().review(_cancel_request(include_confirmation=False))
    decision = result.policy_handoff.payload.decision

    assert decision.status is EligibilityStatus.INSUFFICIENT_FACTS
    assert FactField.USER_CONFIRMED in decision.missing_fact_fields


def test_exchange_workflow_derives_product_facts_from_read_tools() -> None:
    request = CollaborationReviewRequest(
        analysis=OrderSpecialistRequest(
            case_id="case-exchange-1",
            action_type=ActionType.EXCHANGE_ITEMS,
            order_id="#ORDER-1",
            provided_facts=[
                *_common_facts(),
                _fact(FactField.PAYMENT_METHOD_ID, "credit_card_1", FactSourceType.TOOL),
                _fact(FactField.PAYMENT_METHOD_TYPE, "credit_card", FactSourceType.TOOL),
                _fact(FactField.PAYMENT_METHOD_EXISTS, True, FactSourceType.TOOL),
            ],
            exchange_targets=[
                ExchangeTargetRequest(
                    product_id="product-1",
                    current_item_id="item-red",
                    target_item_id="item-blue",
                    source_id="user-message:8",
                )
            ],
        ),
        order_snapshot={"order_id": "#ORDER-1", "status": "delivered"},
        product_snapshots={
            "product-1": {
                "product_id": "product-1",
                "variants": {
                    "item-red": {
                        "available": True,
                        "options": {"color": "red"},
                    },
                    "item-blue": {
                        "available": True,
                        "options": {"color": "blue"},
                    },
                },
            }
        },
    )

    result = SpecialistWorkflow().review(request)
    facts = {fact.field: fact for fact in result.order_handoff.payload.facts}

    assert facts[FactField.TARGET_ITEMS_AVAILABLE].value is True
    assert facts[FactField.TARGET_ITEMS_SAME_PRODUCT].value is True
    assert facts[FactField.TARGET_ITEMS_DIFFERENT_OPTION].value is True
    assert facts[FactField.TARGET_ITEMS_AVAILABLE].derived_from_source_ids
    assert result.policy_handoff.payload.decision.status is EligibilityStatus.ELIGIBLE
    assert [call.tool_name for call in result.order_handoff.payload.tool_calls] == [
        "get_order_details",
        "get_product_details",
    ]


def test_order_status_cannot_be_spoofed_as_a_provided_fact() -> None:
    with pytest.raises(ValidationError, match="order.status must come"):
        OrderSpecialistRequest(
            case_id="case-spoof",
            action_type=ActionType.CANCEL_ORDER,
            order_id="#ORDER-1",
            provided_facts=[_fact(FactField.ORDER_STATUS, "pending", FactSourceType.USER)],
        )


def test_handoff_sender_cannot_be_tampered_with() -> None:
    handoff = SpecialistWorkflow().review(_cancel_request()).order_handoff
    payload = handoff.model_dump(mode="json")
    payload["sender"] = AgentRole.POLICY_SPECIALIST.value

    with pytest.raises(ValidationError):
        OrderToPolicyHandoff.model_validate(payload)


def test_openapi_exposes_collaboration_review() -> None:
    assert tuple(map(int, app.version.split("."))) >= (0, 4, 0)
    assert "/api/v1/collaboration/review" in app.openapi()["paths"]

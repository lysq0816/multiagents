from pathlib import Path

import pytest
from pydantic import ValidationError

from after_sales_agents.api import app
from after_sales_agents.benchmark.tau2_adapter import locate_tau2_root
from after_sales_agents.domain.models import ActionType, Intent
from after_sales_agents.policy.catalog import (
    PolicyRetriever,
    load_policy_catalog,
    validate_catalog_against_source,
)
from after_sales_agents.policy.eligibility import EligibilityEngine
from after_sales_agents.policy.models import (
    BusinessCommitment,
    EligibilityRequest,
    EligibilityStatus,
    FactField,
    FactSourceType,
    PolicySearchRequest,
    RequirementStatus,
    SourceFact,
)


def _fact(
    field: FactField,
    value: object,
    *,
    source_type: FactSourceType = FactSourceType.TOOL,
) -> SourceFact:
    return SourceFact(
        fact_id=f"fact:{field.value}",
        field=field,
        value=value,
        subject_id="#ORDER-1",
        source_type=source_type,
        source_id=f"source:{field.value}",
    )


def _common_facts(status: str) -> list[SourceFact]:
    return [
        _fact(FactField.USER_AUTHENTICATED, True),
        _fact(
            FactField.ACTION_DETAILS_PRESENTED,
            True,
            source_type=FactSourceType.AGENT,
        ),
        _fact(FactField.USER_CONFIRMED, True, source_type=FactSourceType.USER),
        _fact(FactField.ORDER_STATUS, status),
    ]


def _cancel_facts(status: str = "pending") -> list[SourceFact]:
    return [
        *_common_facts(status),
        _fact(FactField.ORDER_ID_CONFIRMED, True, source_type=FactSourceType.USER),
        _fact(
            FactField.CANCEL_REASON,
            "no longer needed",
            source_type=FactSourceType.USER,
        ),
    ]


def test_catalog_excerpts_match_official_policy() -> None:
    try:
        tau2_root = locate_tau2_root()
    except FileNotFoundError:
        pytest.skip("official τ2 checkout is not present")

    catalog = load_policy_catalog()
    validated = validate_catalog_against_source(
        catalog,
        tau2_root / Path(catalog.source_path),
    )

    assert len(validated) == 14
    assert len(validated) == len(set(validated))


def test_chinese_policy_search_finds_cancellation_reason() -> None:
    hits = PolicyRetriever().search(
        PolicySearchRequest(query="取消理由有哪些", intents=[Intent.CANCEL_ORDER])
    )

    assert hits
    assert hits[0].clause.clause_id == "retail.cancel.reason"


def test_action_search_includes_global_write_requirements() -> None:
    hits = PolicyRetriever().search(
        PolicySearchRequest(actions=[ActionType.CANCEL_ORDER], top_k=20)
    )
    clause_ids = {hit.clause.clause_id for hit in hits}

    assert "retail.identity.authentication" in clause_ids
    assert "retail.write.explicit_confirmation" in clause_ids
    assert "retail.cancel.pending_only" in clause_ids


def test_cancel_eligibility_binds_facts_and_policy() -> None:
    decision = EligibilityEngine().evaluate(
        EligibilityRequest(
            action_type=ActionType.CANCEL_ORDER,
            facts=_cancel_facts(),
        )
    )

    assert decision.status is EligibilityStatus.ELIGIBLE
    assert all(check.status is RequirementStatus.PASSED for check in decision.checks)
    assert "fact:order.status" in decision.conclusion.fact_ids
    assert "retail.cancel.pending_only" in decision.conclusion.policy_clause_ids


def test_cancel_rejects_non_pending_order() -> None:
    decision = EligibilityEngine().evaluate(
        EligibilityRequest(
            action_type=ActionType.CANCEL_ORDER,
            facts=_cancel_facts(status="delivered"),
        )
    )

    assert decision.status is EligibilityStatus.INELIGIBLE
    failed = {check.requirement_id for check in decision.checks if check.status == "failed"}
    assert failed == {"cancel.pending_status"}


def test_missing_facts_do_not_produce_an_eligibility_judgment() -> None:
    decision = EligibilityEngine().evaluate(
        EligibilityRequest(action_type=ActionType.CANCEL_ORDER, facts=[])
    )

    assert decision.status is EligibilityStatus.INSUFFICIENT_FACTS
    assert FactField.ORDER_STATUS in decision.missing_fact_fields
    assert decision.conclusion.fact_ids == []
    assert decision.conclusion.policy_clause_ids


def test_return_to_existing_gift_card_is_eligible() -> None:
    facts = [
        *_common_facts("delivered"),
        _fact(FactField.ORDER_ID_CONFIRMED, True, source_type=FactSourceType.USER),
        _fact(FactField.ITEM_IDS, ["item-1"], source_type=FactSourceType.USER),
        _fact(FactField.PAYMENT_METHOD_ID, "gift_card_1"),
        _fact(FactField.PAYMENT_METHOD_EXISTS, True),
        _fact(FactField.PAYMENT_METHOD_TYPE, "gift_card"),
    ]

    decision = EligibilityEngine().evaluate(
        EligibilityRequest(action_type=ActionType.CREATE_RETURN, facts=facts)
    )

    assert decision.status is EligibilityStatus.ELIGIBLE
    assert "retail.return.refund_method" in decision.conclusion.policy_clause_ids


def test_return_rejects_non_original_credit_card() -> None:
    facts = [
        *_common_facts("delivered"),
        _fact(FactField.ORDER_ID_CONFIRMED, True, source_type=FactSourceType.USER),
        _fact(FactField.ITEM_IDS, ["item-1"], source_type=FactSourceType.USER),
        _fact(FactField.PAYMENT_METHOD_ID, "credit_card_1"),
        _fact(FactField.PAYMENT_METHOD_EXISTS, True),
        _fact(FactField.PAYMENT_METHOD_TYPE, "credit_card"),
        _fact(FactField.PAYMENT_METHOD_IS_ORIGINAL, False),
    ]

    decision = EligibilityEngine().evaluate(
        EligibilityRequest(action_type=ActionType.CREATE_RETURN, facts=facts)
    )

    assert decision.status is EligibilityStatus.INELIGIBLE
    assert any(
        check.requirement_id == "return.refund_destination"
        and check.status is RequirementStatus.FAILED
        for check in decision.checks
    )


def test_exchange_rejects_insufficient_gift_card_balance() -> None:
    facts = [
        *_common_facts("delivered"),
        _fact(FactField.ITEM_IDS, ["item-1"], source_type=FactSourceType.USER),
        _fact(FactField.TARGET_ITEMS_AVAILABLE, True),
        _fact(FactField.TARGET_ITEMS_SAME_PRODUCT, True),
        _fact(FactField.TARGET_ITEMS_DIFFERENT_OPTION, True),
        _fact(FactField.PAYMENT_METHOD_ID, "gift_card_1"),
        _fact(FactField.PAYMENT_METHOD_TYPE, "gift_card"),
        _fact(FactField.PAYMENT_METHOD_EXISTS, True),
        _fact(FactField.PRICE_DIFFERENCE, "25.00"),
        _fact(FactField.GIFT_CARD_BALANCE, "20.00"),
    ]

    decision = EligibilityEngine().evaluate(
        EligibilityRequest(action_type=ActionType.EXCHANGE_ITEMS, facts=facts)
    )

    assert decision.status is EligibilityStatus.INELIGIBLE
    assert any(
        check.requirement_id == "exchange.gift_card_balance"
        and check.status is RequirementStatus.FAILED
        for check in decision.checks
    )


def test_business_commitment_requires_fact_and_policy_sources() -> None:
    with pytest.raises(ValidationError):
        BusinessCommitment(
            statement="The refund will definitely arrive tomorrow.",
            fact_ids=[],
            policy_clause_ids=[],
        )


def test_duplicate_fact_fields_are_rejected() -> None:
    duplicate = _fact(FactField.ORDER_STATUS, "pending")
    with pytest.raises(ValidationError, match="each fact field"):
        EligibilityRequest(
            action_type=ActionType.CANCEL_ORDER,
            facts=[duplicate, duplicate.model_copy(update={"fact_id": "fact:duplicate"})],
        )


def test_openapi_exposes_policy_search_and_eligibility() -> None:
    paths = app.openapi()["paths"]

    assert "/api/v1/policy/search" in paths
    assert "/api/v1/policy/eligibility" in paths

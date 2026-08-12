"""Deterministic eligibility checks with fact and policy citations on every conclusion."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from typing import Any

from after_sales_agents.domain.models import ActionType
from after_sales_agents.policy.catalog import PolicyRetriever
from after_sales_agents.policy.models import (
    EligibilityDecision,
    EligibilityRequest,
    EligibilityStatus,
    FactField,
    GroundedConclusion,
    RequirementCheck,
    RequirementStatus,
    SourceFact,
)

ALLOWED_CANCEL_REASONS = {"no longer needed", "ordered by mistake"}


class EligibilityEngine:
    def __init__(self, retriever: PolicyRetriever | None = None) -> None:
        self.retriever = retriever or PolicyRetriever()

    def evaluate(self, request: EligibilityRequest) -> EligibilityDecision:
        facts = {fact.field: fact for fact in request.facts}
        checks: list[RequirementCheck] = []

        def require(
            requirement_id: str,
            description: str,
            fields: list[FactField],
            clause_ids: list[str],
            predicate: Callable[[list[Any]], bool],
        ) -> None:
            for clause_id in clause_ids:
                self.retriever.get_clause(clause_id)
            cited_facts = [facts[field] for field in fields if field in facts]
            if len(cited_facts) != len(fields):
                status = RequirementStatus.MISSING
            else:
                try:
                    status = (
                        RequirementStatus.PASSED
                        if predicate([fact.value for fact in cited_facts])
                        else RequirementStatus.FAILED
                    )
                except (InvalidOperation, TypeError, ValueError):
                    status = RequirementStatus.FAILED
            checks.append(
                RequirementCheck(
                    requirement_id=requirement_id,
                    description=description,
                    status=status,
                    fact_ids=[fact.fact_id for fact in cited_facts],
                    policy_clause_ids=clause_ids,
                )
            )

        self._add_common_checks(require)
        if request.action_type is ActionType.CANCEL_ORDER:
            self._add_cancel_checks(require)
        elif request.action_type is ActionType.CREATE_RETURN:
            self._add_return_checks(require, facts)
        else:
            self._add_exchange_checks(require, facts)

        failed = any(check.status is RequirementStatus.FAILED for check in checks)
        missing = any(check.status is RequirementStatus.MISSING for check in checks)
        if failed:
            status = EligibilityStatus.INELIGIBLE
        elif missing:
            status = EligibilityStatus.INSUFFICIENT_FACTS
        else:
            status = EligibilityStatus.ELIGIBLE

        missing_fields = sorted(
            {
                field
                for check in checks
                if check.status is RequirementStatus.MISSING
                for field in self._requirement_fields(check.requirement_id)
                if field not in facts
            },
            key=str,
        )
        fact_ids = list(dict.fromkeys(fact_id for check in checks for fact_id in check.fact_ids))
        policy_clause_ids = list(
            dict.fromkeys(clause_id for check in checks for clause_id in check.policy_clause_ids)
        )
        summaries = {
            EligibilityStatus.ELIGIBLE: "All cited requirements passed; the action is eligible for planning.",
            EligibilityStatus.INELIGIBLE: "At least one cited policy requirement failed; do not promise or execute the action.",
            EligibilityStatus.INSUFFICIENT_FACTS: "Required source facts are missing; collect them before making an eligibility judgment.",
        }
        return EligibilityDecision(
            action_type=request.action_type,
            status=status,
            checks=checks,
            missing_fact_fields=missing_fields,
            conclusion=GroundedConclusion(
                statement=summaries[status],
                fact_ids=fact_ids,
                policy_clause_ids=policy_clause_ids,
            ),
        )

    @staticmethod
    def _add_common_checks(require: Callable[..., None]) -> None:
        require(
            "common.authentication",
            "The user was authenticated through an allowed lookup.",
            [FactField.USER_AUTHENTICATED],
            ["retail.identity.authentication"],
            lambda values: values[0] is True,
        )
        require(
            "common.action_details",
            "The action details were presented before the write action.",
            [FactField.ACTION_DETAILS_PRESENTED],
            ["retail.write.explicit_confirmation"],
            lambda values: values[0] is True,
        )
        require(
            "common.explicit_confirmation",
            "The user explicitly confirmed the write action.",
            [FactField.USER_CONFIRMED],
            ["retail.write.explicit_confirmation"],
            lambda values: values[0] is True,
        )

    @staticmethod
    def _add_cancel_checks(require: Callable[..., None]) -> None:
        require(
            "cancel.pending_status",
            "The order status is pending.",
            [FactField.ORDER_STATUS],
            ["retail.cancel.pending_only"],
            lambda values: values[0] == "pending",
        )
        require(
            "cancel.order_id_confirmed",
            "The user confirmed the order ID.",
            [FactField.ORDER_ID_CONFIRMED],
            ["retail.cancel.reason"],
            lambda values: values[0] is True,
        )
        require(
            "cancel.allowed_reason",
            "The cancellation reason is allowed by policy.",
            [FactField.CANCEL_REASON],
            ["retail.cancel.reason"],
            lambda values: str(values[0]).strip().lower() in ALLOWED_CANCEL_REASONS,
        )

    @staticmethod
    def _add_return_checks(
        require: Callable[..., None], facts: dict[FactField, SourceFact]
    ) -> None:
        require(
            "return.delivered_status",
            "The order status is delivered.",
            [FactField.ORDER_STATUS],
            ["retail.return.delivered_only"],
            lambda values: values[0] == "delivered",
        )
        require(
            "return.order_id_confirmed",
            "The user confirmed the return order ID.",
            [FactField.ORDER_ID_CONFIRMED],
            ["retail.return.confirm_items"],
            lambda values: values[0] is True,
        )
        require(
            "return.item_list",
            "The user provided at least one item to return.",
            [FactField.ITEM_IDS],
            ["retail.return.confirm_items"],
            lambda values: isinstance(values[0], list) and bool(values[0]),
        )
        require(
            "return.payment_exists",
            "The selected refund payment method exists.",
            [FactField.PAYMENT_METHOD_ID, FactField.PAYMENT_METHOD_EXISTS],
            ["retail.return.refund_method"],
            lambda values: bool(values[0]) and values[1] is True,
        )
        method_fact = facts.get(FactField.PAYMENT_METHOD_TYPE)
        if method_fact is not None and method_fact.value == "gift_card":
            require(
                "return.refund_destination",
                "The refund destination is an existing gift card.",
                [FactField.PAYMENT_METHOD_TYPE],
                ["retail.return.refund_method"],
                lambda values: values[0] == "gift_card",
            )
        else:
            require(
                "return.refund_destination",
                "The refund destination is the original payment method or a gift card.",
                [FactField.PAYMENT_METHOD_TYPE, FactField.PAYMENT_METHOD_IS_ORIGINAL],
                ["retail.return.refund_method"],
                lambda values: values[0] == "gift_card" or values[1] is True,
            )

    @staticmethod
    def _add_exchange_checks(
        require: Callable[..., None], facts: dict[FactField, SourceFact]
    ) -> None:
        require(
            "exchange.delivered_status",
            "The order status is delivered.",
            [FactField.ORDER_STATUS],
            ["retail.exchange.delivered_only"],
            lambda values: values[0] == "delivered",
        )
        require(
            "exchange.item_list",
            "The user provided at least one item to exchange.",
            [FactField.ITEM_IDS],
            ["retail.exchange.delivered_only"],
            lambda values: isinstance(values[0], list) and bool(values[0]),
        )
        for requirement_id, description, field in (
            (
                "exchange.targets_available",
                "Every target variant is available.",
                FactField.TARGET_ITEMS_AVAILABLE,
            ),
            (
                "exchange.same_product",
                "Every target variant belongs to the same product.",
                FactField.TARGET_ITEMS_SAME_PRODUCT,
            ),
            (
                "exchange.different_option",
                "Every target variant uses a different product option.",
                FactField.TARGET_ITEMS_DIFFERENT_OPTION,
            ),
        ):
            require(
                requirement_id,
                description,
                [field],
                ["retail.exchange.same_product_available"],
                lambda values: values[0] is True,
            )
        require(
            "exchange.payment_exists",
            "The user provided an existing payment method for the price difference.",
            [
                FactField.PAYMENT_METHOD_ID,
                FactField.PAYMENT_METHOD_TYPE,
                FactField.PAYMENT_METHOD_EXISTS,
            ],
            ["retail.exchange.payment"],
            lambda values: bool(values[0]) and bool(values[1]) and values[2] is True,
        )

        method = facts.get(FactField.PAYMENT_METHOD_TYPE)
        if method is not None and method.value == "gift_card":
            require(
                "exchange.gift_card_balance",
                "The gift card balance covers a positive price difference.",
                [FactField.PRICE_DIFFERENCE, FactField.GIFT_CARD_BALANCE],
                ["retail.exchange.payment"],
                lambda values: (
                    Decimal(str(values[0])) <= 0
                    or Decimal(str(values[1])) >= Decimal(str(values[0]))
                ),
            )

    @staticmethod
    def _requirement_fields(requirement_id: str) -> list[FactField]:
        mapping = {
            "common.authentication": [FactField.USER_AUTHENTICATED],
            "common.action_details": [FactField.ACTION_DETAILS_PRESENTED],
            "common.explicit_confirmation": [FactField.USER_CONFIRMED],
            "cancel.pending_status": [FactField.ORDER_STATUS],
            "cancel.order_id_confirmed": [FactField.ORDER_ID_CONFIRMED],
            "cancel.allowed_reason": [FactField.CANCEL_REASON],
            "return.delivered_status": [FactField.ORDER_STATUS],
            "return.order_id_confirmed": [FactField.ORDER_ID_CONFIRMED],
            "return.item_list": [FactField.ITEM_IDS],
            "return.payment_exists": [
                FactField.PAYMENT_METHOD_ID,
                FactField.PAYMENT_METHOD_EXISTS,
            ],
            "return.refund_destination": [
                FactField.PAYMENT_METHOD_TYPE,
                FactField.PAYMENT_METHOD_IS_ORIGINAL,
            ],
            "exchange.delivered_status": [FactField.ORDER_STATUS],
            "exchange.item_list": [FactField.ITEM_IDS],
            "exchange.targets_available": [FactField.TARGET_ITEMS_AVAILABLE],
            "exchange.same_product": [FactField.TARGET_ITEMS_SAME_PRODUCT],
            "exchange.different_option": [FactField.TARGET_ITEMS_DIFFERENT_OPTION],
            "exchange.payment_exists": [
                FactField.PAYMENT_METHOD_ID,
                FactField.PAYMENT_METHOD_TYPE,
                FactField.PAYMENT_METHOD_EXISTS,
            ],
            "exchange.gift_card_balance": [
                FactField.PRICE_DIFFERENCE,
                FactField.GIFT_CARD_BALANCE,
            ],
        }
        return mapping[requirement_id]

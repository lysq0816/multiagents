"""Read-only order specialist that converts tool responses into source facts."""

from __future__ import annotations

from after_sales_agents.agents.models import (
    OrderFactBundle,
    OrderSpecialistRequest,
    OrderToPolicyHandoff,
)
from after_sales_agents.agents.permissions import SnapshotRetailTools, ToolName
from after_sales_agents.domain.models import ActionType, AgentRole
from after_sales_agents.policy.models import FactField, FactSourceType, SourceFact


class OrderSpecialist:
    role = AgentRole.ORDER_SPECIALIST

    def analyze(
        self,
        request: OrderSpecialistRequest,
        tools: SnapshotRetailTools,
    ) -> OrderToPolicyHandoff:
        start_index = len(tools.call_records)
        order_result = tools.call(
            self.role,
            ToolName.GET_ORDER_DETAILS,
            {"order_id": request.order_id},
        )
        status = str(order_result.data.get("status") or "")
        facts = [*request.provided_facts]
        facts.append(
            SourceFact(
                fact_id=f"fact:{request.case_id}:order-status",
                field=FactField.ORDER_STATUS,
                value=status,
                subject_id=request.order_id,
                source_type=FactSourceType.TOOL,
                source_id=order_result.call.call_id,
            )
        )

        if request.action_type is ActionType.EXCHANGE_ITEMS and request.exchange_targets:
            existing_fields = {fact.field for fact in facts}
            facts.extend(
                fact
                for fact in self._exchange_facts(request, tools)
                if fact.field not in existing_fields
            )

        return OrderToPolicyHandoff(
            handoff_id=(
                f"{request.case_id}:order-to-policy:{request.action_type.value}:{request.order_id}"
            ),
            case_id=request.case_id,
            payload=OrderFactBundle(
                case_id=request.case_id,
                action_type=request.action_type,
                order_id=request.order_id,
                facts=facts,
                tool_calls=tools.call_records[start_index:],
            ),
        )

    def _exchange_facts(
        self,
        request: OrderSpecialistRequest,
        tools: SnapshotRetailTools,
    ) -> list[SourceFact]:
        checks: list[tuple[bool, bool, bool]] = []
        product_call_ids: list[str] = []
        user_source_ids: list[str] = []

        for target in request.exchange_targets:
            result = tools.call(
                self.role,
                ToolName.GET_PRODUCT_DETAILS,
                {"product_id": target.product_id},
            )
            product_call_ids.append(result.call.call_id)
            user_source_ids.append(target.source_id)
            variants = result.data.get("variants") or {}
            current = variants.get(target.current_item_id)
            replacement = variants.get(target.target_item_id)
            same_product = current is not None and replacement is not None
            available = bool(replacement and replacement.get("available") is True)
            different_option = bool(
                same_product and current.get("options") != replacement.get("options")
            )
            checks.append((available, same_product, different_option))

        derived_source = f"order-specialist:{request.case_id}:exchange-validation"
        common = {
            "subject_id": request.order_id,
            "source_type": FactSourceType.AGENT,
            "source_id": derived_source,
        }
        facts = [
            SourceFact(
                fact_id=f"fact:{request.case_id}:exchange-item-ids",
                field=FactField.ITEM_IDS,
                value=[target.current_item_id for target in request.exchange_targets],
                derived_from_source_ids=user_source_ids,
                **common,
            ),
            SourceFact(
                fact_id=f"fact:{request.case_id}:exchange-target-item-ids",
                field=FactField.TARGET_ITEM_IDS,
                value=[target.target_item_id for target in request.exchange_targets],
                derived_from_source_ids=user_source_ids,
                **common,
            ),
            SourceFact(
                fact_id=f"fact:{request.case_id}:targets-available",
                field=FactField.TARGET_ITEMS_AVAILABLE,
                value=all(check[0] for check in checks),
                derived_from_source_ids=product_call_ids,
                **common,
            ),
            SourceFact(
                fact_id=f"fact:{request.case_id}:targets-same-product",
                field=FactField.TARGET_ITEMS_SAME_PRODUCT,
                value=all(check[1] for check in checks),
                derived_from_source_ids=product_call_ids,
                **common,
            ),
            SourceFact(
                fact_id=f"fact:{request.case_id}:targets-different-option",
                field=FactField.TARGET_ITEMS_DIFFERENT_OPTION,
                value=all(check[2] for check in checks),
                derived_from_source_ids=product_call_ids,
                **common,
            ),
        ]
        return facts

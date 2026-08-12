"""Policy specialist that can retrieve clauses and evaluate, but cannot read or write orders."""

from __future__ import annotations

from after_sales_agents.agents.models import (
    OrderToPolicyHandoff,
    PolicyReviewBundle,
    PolicyToPlannerHandoff,
)
from after_sales_agents.agents.permissions import ToolName, ToolPermissionGuard
from after_sales_agents.domain.models import ActionType, AgentRole, Intent
from after_sales_agents.policy.catalog import PolicyRetriever
from after_sales_agents.policy.eligibility import EligibilityEngine
from after_sales_agents.policy.models import EligibilityRequest, PolicySearchRequest

INTENT_BY_ACTION = {
    ActionType.CANCEL_ORDER: Intent.CANCEL_ORDER,
    ActionType.CREATE_RETURN: Intent.RETURN_ITEMS,
    ActionType.EXCHANGE_ITEMS: Intent.EXCHANGE_ITEMS,
}


class PolicySpecialist:
    role = AgentRole.POLICY_SPECIALIST

    def __init__(
        self,
        retriever: PolicyRetriever | None = None,
        engine: EligibilityEngine | None = None,
        guard: ToolPermissionGuard | None = None,
    ) -> None:
        self.retriever = retriever or PolicyRetriever()
        self.engine = engine or EligibilityEngine(self.retriever)
        self.guard = guard or ToolPermissionGuard()

    def review(self, handoff: OrderToPolicyHandoff) -> PolicyToPlannerHandoff:
        action_type = handoff.payload.action_type
        self.guard.ensure_allowed(self.role, ToolName.POLICY_SEARCH)
        hits = self.retriever.search(
            PolicySearchRequest(
                query=f"eligibility requirements for {action_type.value}",
                intents=[INTENT_BY_ACTION[action_type]],
                actions=[action_type],
                top_k=20,
            )
        )

        self.guard.ensure_allowed(self.role, ToolName.POLICY_ELIGIBILITY)
        decision = self.engine.evaluate(
            EligibilityRequest(action_type=action_type, facts=handoff.payload.facts)
        )
        return PolicyToPlannerHandoff(
            handoff_id=(
                f"{handoff.case_id}:policy-to-planner:"
                f"{action_type.value}:{handoff.payload.order_id}"
            ),
            case_id=handoff.case_id,
            payload=PolicyReviewBundle(
                case_id=handoff.case_id,
                action_type=action_type,
                order_id=handoff.payload.order_id,
                facts=handoff.payload.facts,
                retrieved_policy=hits,
                decision=decision,
            ),
        )

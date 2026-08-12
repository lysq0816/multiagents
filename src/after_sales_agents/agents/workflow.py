"""Day 4 deterministic orchestration for the two specialist agents."""

from __future__ import annotations

from after_sales_agents.agents.models import (
    CollaborationReviewRequest,
    SpecialistCollaborationResult,
)
from after_sales_agents.agents.order_specialist import OrderSpecialist
from after_sales_agents.agents.permissions import SnapshotRetailTools, ToolPermissionGuard
from after_sales_agents.agents.policy_specialist import PolicySpecialist


class SpecialistWorkflow:
    def __init__(self, guard: ToolPermissionGuard | None = None) -> None:
        self.guard = guard or ToolPermissionGuard()
        self.order_specialist = OrderSpecialist()
        self.policy_specialist = PolicySpecialist(guard=self.guard)

    def review(self, request: CollaborationReviewRequest) -> SpecialistCollaborationResult:
        tools = SnapshotRetailTools(
            order_snapshot=request.order_snapshot,
            product_snapshots=request.product_snapshots,
            guard=self.guard,
        )
        order_handoff = self.order_specialist.analyze(request.analysis, tools)
        policy_handoff = self.policy_specialist.review(order_handoff)
        return SpecialistCollaborationResult(
            order_handoff=order_handoff,
            policy_handoff=policy_handoff,
        )

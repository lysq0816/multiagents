"""End-to-end Day 5 orchestration from read-only specialists to a gated plan."""

from __future__ import annotations

from after_sales_agents.agents.permissions import ToolPermissionGuard
from after_sales_agents.agents.workflow import SpecialistWorkflow
from after_sales_agents.planning.models import (
    PlannerRequest,
    PlanningWorkflowRequest,
    PlanningWorkflowResult,
)
from after_sales_agents.planning.planner import CandidateActionPlanner


class PlanningWorkflow:
    def __init__(self, guard: ToolPermissionGuard | None = None) -> None:
        self.guard = guard or ToolPermissionGuard()
        self.specialists = SpecialistWorkflow(self.guard)
        self.planner = CandidateActionPlanner()

    def review(self, request: PlanningWorkflowRequest) -> PlanningWorkflowResult:
        specialist_results = []
        order_handoff_counts: dict[str, int] = {}
        policy_handoff_counts: dict[str, int] = {}
        for review_request in request.reviews:
            result = self.specialists.review(review_request)
            order_handoff = result.order_handoff
            policy_handoff = result.policy_handoff

            order_handoff_counts[order_handoff.handoff_id] = (
                order_handoff_counts.get(order_handoff.handoff_id, 0) + 1
            )
            policy_handoff_counts[policy_handoff.handoff_id] = (
                policy_handoff_counts.get(policy_handoff.handoff_id, 0) + 1
            )
            order_occurrence = order_handoff_counts[order_handoff.handoff_id]
            policy_occurrence = policy_handoff_counts[policy_handoff.handoff_id]
            if order_occurrence > 1:
                order_handoff = order_handoff.model_copy(
                    update={
                        "handoff_id": (f"{order_handoff.handoff_id}:occurrence-{order_occurrence}")
                    }
                )
            if policy_occurrence > 1:
                policy_handoff = policy_handoff.model_copy(
                    update={
                        "handoff_id": (
                            f"{policy_handoff.handoff_id}:occurrence-{policy_occurrence}"
                        )
                    }
                )
            specialist_results.append(
                result.model_copy(
                    update={
                        "order_handoff": order_handoff,
                        "policy_handoff": policy_handoff,
                    }
                )
            )

        case_id = request.reviews[0].analysis.case_id
        plan = self.planner.plan(
            PlannerRequest(
                case_id=case_id,
                handoffs=[result.policy_handoff for result in specialist_results],
            )
        )
        return PlanningWorkflowResult(
            specialist_results=specialist_results,
            plan=plan,
        )

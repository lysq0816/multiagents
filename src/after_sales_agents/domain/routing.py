"""Deterministic routing rules that decide when collaboration is justified."""

from __future__ import annotations

from after_sales_agents.domain.models import (
    ActionType,
    AgentRole,
    RiskLevel,
    RouteKind,
    RoutingDecision,
    TicketIntake,
)


class DifficultyRouter:
    """Route a structured ticket without relying on an LLM judgment."""

    def route(self, ticket: TicketIntake) -> RoutingDecision:
        consequential_actions = [
            action for action in ticket.requested_actions if action.is_consequential
        ]
        approval_required = bool(consequential_actions)

        if ticket.missing_information:
            return RoutingDecision(
                route=RouteKind.NEEDS_CLARIFICATION,
                risk_level=self._risk_level(ticket, consequential_actions),
                reasons=["missing_information"],
                specialists=[AgentRole.CUSTOMER_SERVICE],
                approval_required=approval_required,
                can_execute_now=False,
            )

        complexity_reasons: list[str] = []
        if len(ticket.intents) > 1:
            complexity_reasons.append("multiple_intents")
        if len(ticket.order_ids) > 1:
            complexity_reasons.append("multiple_orders")
        if len(consequential_actions) > 1:
            complexity_reasons.append("multiple_consequential_actions")
        if ticket.has_policy_conflict:
            complexity_reasons.append("policy_conflict")
        if ticket.requires_money_movement and ticket.requires_inventory_movement:
            complexity_reasons.append("money_and_inventory_coupled")

        risk_level = self._risk_level(ticket, consequential_actions)
        if complexity_reasons:
            specialists = [
                AgentRole.ORDER_SPECIALIST,
                AgentRole.POLICY_SPECIALIST,
            ]
            if ticket.requires_inventory_movement or any(
                action in {ActionType.EXCHANGE_ITEMS, ActionType.RESHIP_ITEMS}
                for action in consequential_actions
            ):
                specialists.append(AgentRole.INVENTORY_SPECIALIST)
            specialists.extend([AgentRole.PLANNER, AgentRole.AUDITOR])
            return RoutingDecision(
                route=RouteKind.MULTI_AGENT,
                risk_level=risk_level,
                reasons=complexity_reasons,
                specialists=specialists,
                approval_required=approval_required,
                can_execute_now=not approval_required or ticket.user_confirmed,
            )

        specialists = [AgentRole.CUSTOMER_SERVICE]
        if approval_required:
            specialists.append(AgentRole.AUDITOR)
        return RoutingDecision(
            route=RouteKind.SINGLE_AGENT,
            risk_level=risk_level,
            reasons=["routine_ticket"],
            specialists=specialists,
            approval_required=approval_required,
            can_execute_now=not approval_required or ticket.user_confirmed,
        )

    @staticmethod
    def _risk_level(
        ticket: TicketIntake,
        consequential_actions: list[ActionType],
    ) -> RiskLevel:
        if (
            ticket.has_policy_conflict
            or len(consequential_actions) > 1
            or (ticket.requires_money_movement and ticket.requires_inventory_movement)
        ):
            return RiskLevel.HIGH
        if consequential_actions or ticket.requires_money_movement:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

import unittest

from after_sales_agents.domain.models import (
    ActionType,
    AgentRole,
    ApprovalStatus,
    CaseState,
    Intent,
    ProposedAction,
    RiskLevel,
    RouteKind,
    TicketIntake,
)
from after_sales_agents.domain.routing import DifficultyRouter


class DifficultyRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.router = DifficultyRouter()

    def test_read_only_ticket_uses_single_agent_without_approval(self) -> None:
        decision = self.router.route(
            TicketIntake(
                ticket_id="t-1",
                user_message="帮我查一下订单",
                intents=[Intent.ORDER_LOOKUP],
                order_ids=["o-1"],
                requested_actions=[ActionType.READ_ORDER],
            )
        )

        self.assertEqual(decision.route, RouteKind.SINGLE_AGENT)
        self.assertEqual(decision.risk_level, RiskLevel.LOW)
        self.assertFalse(decision.approval_required)
        self.assertTrue(decision.can_execute_now)

    def test_routine_cancellation_requires_auditor_and_confirmation(self) -> None:
        decision = self.router.route(
            TicketIntake(
                ticket_id="t-2",
                user_message="取消这个未发货订单",
                intents=[Intent.CANCEL_ORDER],
                order_ids=["o-2"],
                requested_actions=[ActionType.CANCEL_ORDER],
            )
        )

        self.assertEqual(decision.route, RouteKind.SINGLE_AGENT)
        self.assertEqual(decision.risk_level, RiskLevel.MEDIUM)
        self.assertTrue(decision.approval_required)
        self.assertFalse(decision.can_execute_now)
        self.assertIn(AgentRole.AUDITOR, decision.specialists)

    def test_multiple_intents_trigger_multi_agent_route(self) -> None:
        decision = self.router.route(
            TicketIntake(
                ticket_id="t-3",
                user_message="退掉衬衫并换一双鞋",
                intents=[Intent.RETURN_ITEMS, Intent.EXCHANGE_ITEMS],
                order_ids=["o-3"],
                requested_actions=[
                    ActionType.CREATE_RETURN,
                    ActionType.EXCHANGE_ITEMS,
                ],
                requires_money_movement=True,
                requires_inventory_movement=True,
            )
        )

        self.assertEqual(decision.route, RouteKind.MULTI_AGENT)
        self.assertEqual(decision.risk_level, RiskLevel.HIGH)
        self.assertIn("multiple_intents", decision.reasons)
        self.assertIn(AgentRole.ORDER_SPECIALIST, decision.specialists)
        self.assertIn(AgentRole.POLICY_SPECIALIST, decision.specialists)
        self.assertIn(AgentRole.INVENTORY_SPECIALIST, decision.specialists)
        self.assertIn(AgentRole.AUDITOR, decision.specialists)

    def test_multiple_orders_trigger_multi_agent_route(self) -> None:
        decision = self.router.route(
            TicketIntake(
                ticket_id="t-4",
                user_message="查询并处理这两个订单",
                intents=[Intent.ORDER_LOOKUP],
                order_ids=["o-4", "o-5"],
                requested_actions=[ActionType.READ_ORDER],
            )
        )

        self.assertEqual(decision.route, RouteKind.MULTI_AGENT)
        self.assertIn("multiple_orders", decision.reasons)

    def test_missing_information_routes_to_clarification(self) -> None:
        decision = self.router.route(
            TicketIntake(
                ticket_id="t-5",
                user_message="我要退货",
                intents=[Intent.RETURN_ITEMS],
                requested_actions=[ActionType.CREATE_RETURN],
                missing_information=["order_id"],
            )
        )

        self.assertEqual(decision.route, RouteKind.NEEDS_CLARIFICATION)
        self.assertEqual(decision.specialists, [AgentRole.CUSTOMER_SERVICE])
        self.assertFalse(decision.can_execute_now)

    def test_policy_conflict_is_high_risk(self) -> None:
        decision = self.router.route(
            TicketIntake(
                ticket_id="t-6",
                user_message="超过期限但仍要退货",
                intents=[Intent.RETURN_ITEMS],
                order_ids=["o-6"],
                requested_actions=[ActionType.CREATE_RETURN],
                has_policy_conflict=True,
            )
        )

        self.assertEqual(decision.route, RouteKind.MULTI_AGENT)
        self.assertEqual(decision.risk_level, RiskLevel.HIGH)
        self.assertIn("policy_conflict", decision.reasons)

    def test_case_state_blocks_unapproved_consequential_actions(self) -> None:
        state = CaseState(
            ticket_id="t-7",
            candidate_actions=[
                ProposedAction(action_type=ActionType.CREATE_RETURN, order_id="o-7")
            ],
            approval_status=ApprovalStatus.PENDING,
        )

        self.assertTrue(state.has_pending_consequential_actions)
        self.assertFalse(state.can_execute_consequential_actions)

        approved_state = state.model_copy(update={"approval_status": ApprovalStatus.APPROVED})
        self.assertTrue(approved_state.can_execute_consequential_actions)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import importlib.util
import unittest
from unittest.mock import patch

TAU2_AVAILABLE = importlib.util.find_spec("tau2") is not None

if TAU2_AVAILABLE:
    from tau2.data_model.message import AssistantMessage, ToolCall, UserMessage
    from tau2.environment.tool import as_tool

    from after_sales_agents.benchmark.tau2_multiagent_core import (
        AuditDecision,
        PolicyReview,
    )
    from after_sales_agents.benchmark.tau2_multiagent_runtime import RoutedTau2MultiAgent


def exchange_delivered_order_items(
    order_id: str,
    item_ids: list[str],
    new_item_ids: list[str],
    payment_method_id: str,
) -> str:
    """Exchange delivered items using the official Retail argument shape."""

    return order_id + payment_method_id + "".join(item_ids + new_item_ids)


def get_order_details(order_id: str) -> str:
    """Read one order."""

    return order_id


def get_product_details(product_id: str) -> str:
    """Read one product."""

    return product_id


@unittest.skipUnless(TAU2_AVAILABLE, "tau2 is exercised in its official virtual environment")
class Tau2MultiAgentRuntimeOfficialTests(unittest.TestCase):
    @staticmethod
    def _write_candidate() -> AssistantMessage:
        return AssistantMessage(
            role="assistant",
            content=None,
            tool_calls=[
                ToolCall(
                    id="call-1",
                    name="exchange_delivered_order_items",
                    arguments={
                        "order_id": "#W2378156",
                        "item_ids": ["1151293680"],
                        "new_item_ids": ["7706410293"],
                        "payment_method_id": "credit_card_9513926",
                    },
                    requestor="assistant",
                )
            ],
        )

    def test_reviewers_receive_authoritative_candidate_tool_schema(self) -> None:
        agent = RoutedTau2MultiAgent(
            tools=[as_tool(exchange_delivered_order_items)],
            domain_policy="Only explicit policy requirements may block an exchange.",
            llm="fake/model",
        )
        state = agent.get_init_state([UserMessage(role="user", content="Yes, exchange it.")])
        captured_payloads: list[dict[str, object]] = []

        def fake_structured_call(**kwargs: object) -> PolicyReview | AuditDecision:
            payload = kwargs["payload"]
            self.assertIsInstance(payload, dict)
            captured_payloads.append(payload)
            if kwargs["model_type"] is PolicyReview:
                return PolicyReview(
                    candidate_allowed=True,
                    confirmation_required=True,
                    confirmation_present=True,
                )
            return AuditDecision(approved=True)

        trace: dict[str, object] = {"policy_reviews": [], "audits": []}
        with patch.object(agent, "_structured_call", side_effect=fake_structured_call):
            policy, audit = agent._audit_candidate(self._write_candidate(), state, [], trace)

        self.assertIsNotNone(policy)
        self.assertTrue(policy.candidate_allowed)
        self.assertTrue(audit.approved)
        for payload in captured_payloads:
            self.assertEqual(
                payload["available_tool_names"],
                ["exchange_delivered_order_items"],
            )
            schemas = payload["candidate_tool_schemas"]
            self.assertIsInstance(schemas, list)
            self.assertEqual(len(schemas), 1)
            parameters = schemas[0]["function"]["parameters"]["properties"]
            self.assertEqual(
                set(parameters),
                {
                    "order_id",
                    "item_ids",
                    "new_item_ids",
                    "payment_method_id",
                },
            )
            self.assertNotIn("price_difference", parameters)

    def test_rejected_write_cannot_fall_through_to_a_false_success_text(self) -> None:
        agent = RoutedTau2MultiAgent(tools=[], domain_policy="policy", llm="fake/model")
        state = agent.get_init_state([UserMessage(role="user", content="Yes, proceed.")])
        policy = PolicyReview(
            candidate_allowed=False,
            confirmation_required=True,
            confirmation_present=True,
            violated_rules=["candidate rejected"],
        )
        audit = AuditDecision(approved=False, issues=["candidate rejected"])
        false_success = AssistantMessage(
            role="assistant",
            content="The exchange has been submitted successfully.",
        )
        trace: dict[str, object] = {"policy_reviews": [], "audits": []}

        with (
            patch.object(agent, "_audit_candidate", return_value=(policy, audit)),
            patch.object(agent, "_coordinator_generate", return_value=false_success),
        ):
            output = agent._review_and_repair(self._write_candidate(), state, [], trace)

        self.assertIsNone(output.tool_calls)
        self.assertIsNotNone(output.content)
        self.assertIn("did not execute that requested database change", output.content)
        self.assertNotIn("submitted successfully", output.content)
        self.assertEqual(trace["repair_outcome"], "blocked_after_unsafe_non_tool_repair")

    def test_raw_tool_markup_retry_cannot_accept_empty_tools_or_false_success(self) -> None:
        agent = RoutedTau2MultiAgent(
            tools=[as_tool(exchange_delivered_order_items)],
            domain_policy="policy",
            llm="fake/model",
        )
        state = agent.get_init_state([])
        raw_markup = AssistantMessage(
            role="assistant",
            content=('<｜｜DSML｜｜tool_calls><｜｜DSML｜｜invoke name="exchange_order_items">'),
        )
        false_success = AssistantMessage(
            role="assistant",
            content="The exchange has been submitted successfully.",
            tool_calls=[],
        )

        with patch.object(
            agent,
            "_coordinator_generate",
            side_effect=[raw_markup, false_success],
        ):
            output, _ = agent.generate_next_message(
                UserMessage(role="user", content="Hello."),
                state,
            )

        self.assertIsNone(output.tool_calls)
        self.assertIn("did not execute that requested database change", output.content)
        self.assertNotIn("submitted successfully", output.content)
        trace = output.raw_data["after_sales_multiagent_trace"]
        self.assertEqual(trace["repair_outcome"], "blocked_invalid_tool_markup")

    def test_multiple_or_unknown_tool_calls_are_blocked_without_truncation(self) -> None:
        agent = RoutedTau2MultiAgent(
            tools=[as_tool(exchange_delivered_order_items)],
            domain_policy="policy",
            llm="fake/model",
        )
        known = self._write_candidate().tool_calls[0]
        second = known.model_copy(update={"id": "call-2"})
        multiple = AssistantMessage(
            role="assistant",
            content=None,
            tool_calls=[known, second],
        )
        unknown = AssistantMessage(
            role="assistant",
            content=None,
            tool_calls=[known.model_copy(update={"name": "exchange_order_items"})],
        )

        blocked_multiple = agent._normalize_candidate(multiple)
        blocked_unknown = agent._normalize_candidate(unknown)

        self.assertIsNone(blocked_multiple.tool_calls)
        self.assertIn("did not execute that requested database change", blocked_multiple.content)
        self.assertIsNone(blocked_unknown.tool_calls)
        self.assertIn("did not execute that requested database change", blocked_unknown.content)

    def test_registered_read_batch_is_serialized_and_recorded(self) -> None:
        agent = RoutedTau2MultiAgent(
            tools=[as_tool(get_order_details), as_tool(get_product_details)],
            domain_policy="policy",
            llm="fake/model",
        )
        batch = AssistantMessage(
            role="assistant",
            content=None,
            tool_calls=[
                ToolCall(
                    id="read-1",
                    name="get_order_details",
                    arguments={"order_id": "#W2378156"},
                    requestor="assistant",
                ),
                ToolCall(
                    id="read-2",
                    name="get_product_details",
                    arguments={"product_id": "1656367028"},
                    requestor="assistant",
                ),
            ],
        )
        trace: dict[str, object] = {}

        normalized = agent._normalize_candidate(batch, trace)

        self.assertEqual(len(normalized.tool_calls), 1)
        self.assertEqual(normalized.tool_calls[0].name, "get_order_details")
        self.assertEqual(
            trace["normalized_tool_batches"],
            [
                {
                    "reason": "serialized_read_tool_batch",
                    "returned_tool": "get_order_details",
                    "deferred_tools": ["get_product_details"],
                }
            ],
        )

    def test_two_rejected_audits_end_without_a_third_coordinator_call(self) -> None:
        agent = RoutedTau2MultiAgent(
            tools=[as_tool(exchange_delivered_order_items)],
            domain_policy="policy",
            llm="fake/model",
        )
        state = agent.get_init_state([UserMessage(role="user", content="Yes, proceed.")])
        policy = PolicyReview(
            candidate_allowed=False,
            confirmation_required=True,
            confirmation_present=True,
            violated_rules=["candidate rejected"],
        )
        audit = AuditDecision(approved=False, issues=["candidate rejected"])
        repaired_write = self._write_candidate().model_copy(deep=True)
        trace: dict[str, object] = {"policy_reviews": [], "audits": []}

        with (
            patch.object(
                agent,
                "_audit_candidate",
                side_effect=[(policy, audit), (policy, audit)],
            ) as audit_mock,
            patch.object(
                agent,
                "_coordinator_generate",
                return_value=repaired_write,
            ) as coordinator_mock,
        ):
            output = agent._review_and_repair(self._write_candidate(), state, [], trace)

        self.assertEqual(audit_mock.call_count, 2)
        self.assertEqual(coordinator_mock.call_count, 1)
        self.assertIsNone(output.tool_calls)
        self.assertIn("did not execute that requested database change", output.content)
        self.assertEqual(trace["repair_outcome"], "blocked_pending_user_clarification")

    def test_raw_markup_can_recover_to_one_registered_approved_tool(self) -> None:
        agent = RoutedTau2MultiAgent(
            tools=[as_tool(exchange_delivered_order_items)],
            domain_policy="policy",
            llm="fake/model",
        )
        state = agent.get_init_state([])
        raw_markup = AssistantMessage(
            role="assistant",
            content=('<｜｜DSML｜｜tool_calls><｜｜DSML｜｜invoke name="exchange_order_items">'),
        )
        approved_write = self._write_candidate()
        policy = PolicyReview(
            candidate_allowed=True,
            confirmation_required=True,
            confirmation_present=True,
        )
        audit = AuditDecision(approved=True)

        with (
            patch.object(
                agent,
                "_coordinator_generate",
                side_effect=[raw_markup, approved_write],
            ),
            patch.object(agent, "_audit_candidate", return_value=(policy, audit)),
        ):
            output, _ = agent.generate_next_message(
                UserMessage(role="user", content="Hello."),
                state,
            )

        self.assertEqual(len(output.tool_calls), 1)
        self.assertEqual(output.tool_calls[0].name, "exchange_delivered_order_items")


if __name__ == "__main__":
    unittest.main()

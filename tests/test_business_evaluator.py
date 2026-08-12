import copy

from after_sales_agents.benchmark.business_evaluator import (
    evaluate_business_compatibility,
)


def _task(reason_for_call: str = "Please cancel the order if no cheaper option works.") -> dict:
    return {
        "id": "38",
        "user_scenario": {"instructions": {"reason_for_call": reason_for_call}},
        "evaluation_criteria": {
            "actions": [
                {
                    "name": "calculate",
                    "arguments": {"expression": "466.75 + 288.82"},
                },
                {
                    "name": "cancel_pending_order",
                    "arguments": {
                        "order_id": "#W9348897",
                        "reason": "no longer needed",
                    },
                },
            ],
            "nl_assertions": ["State the most expensive item."],
        },
    }


def _simulation() -> dict:
    return {
        "task_id": "38",
        "reward_info": {
            "reward": 0.0,
            "action_checks": [
                {
                    "action": {"name": "calculate"},
                    "action_match": True,
                },
                {
                    "action": {"name": "cancel_pending_order"},
                    "action_match": False,
                },
            ],
            "nl_assertions": [{"met": True}],
        },
        "messages": [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "cancel-1",
                        "name": "cancel_pending_order",
                        "arguments": {
                            "order_id": "#W9348897",
                            "reason": "ordered by mistake",
                        },
                    }
                ],
            },
            {
                "id": "cancel-1",
                "role": "tool",
                "error": False,
                "content": ('{"status": "cancelled", "cancel_reason": "ordered by mistake"}'),
            },
        ],
    }


def test_accepts_policy_reason_when_scenario_does_not_choose_one() -> None:
    report = evaluate_business_compatibility(_task(), _simulation())

    assert report["official_reward"] == 0.0
    assert report["business_reward"] == 1.0
    assert report["reason_compatibility_applied"] is True


def test_rejects_missing_required_calculator_action() -> None:
    simulation = _simulation()
    simulation["reward_info"]["action_checks"][0]["action_match"] = False

    report = evaluate_business_compatibility(_task(), simulation)

    assert report["business_reward"] == 0.0
    assert report["checks"]["non_cancel_actions_match"] is False


def test_accepts_reordered_addends_only_when_calculator_succeeds() -> None:
    simulation = _simulation()
    simulation["reward_info"]["action_checks"][0] = {
        "action": {
            "name": "calculate",
            "arguments": {"expression": "466.75 + 288.82"},
        },
        "action_match": False,
    }
    simulation["messages"][0:0] = [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "calculate-1",
                    "name": "calculate",
                    "arguments": {"expression": "288.82 + 466.75"},
                }
            ],
        },
        {
            "id": "calculate-1",
            "role": "tool",
            "error": False,
            "content": "755.57",
        },
    ]

    report = evaluate_business_compatibility(_task(), simulation)

    assert report["business_reward"] == 1.0
    assert report["calculation_compatibility_applied"] is True


def test_rejects_alternate_reason_when_scenario_specifies_gold_reason() -> None:
    report = evaluate_business_compatibility(
        _task("Cancel it because it is no longer needed."),
        copy.deepcopy(_simulation()),
    )

    assert report["business_reward"] == 0.0
    assert report["checks"]["cancel_reason_allowed"] is False
    assert report["reason_compatibility_applied"] is False

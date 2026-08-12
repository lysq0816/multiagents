import copy
import unittest
from collections import Counter

from after_sales_agents.benchmark.models import RetailIntent
from after_sales_agents.benchmark.tau2_adapter import (
    WRITE_TOOL_BY_INTENT,
    load_manifest,
    locate_tau2_root,
    validate_official_subset,
    validate_subset,
)


class Tau2AdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = load_manifest()
        self.tasks = {}
        self.splits = {"base": [], "train": [], "test": []}
        for selection in self.manifest.tasks:
            self.tasks[selection.task_id] = {
                "id": selection.task_id,
                "user_scenario": {
                    "instructions": {
                        "reason_for_call": f"Synthetic task {selection.task_id}",
                        "known_info": "Synthetic user",
                    }
                },
                "evaluation_criteria": {
                    "actions": [
                        {
                            "name": WRITE_TOOL_BY_INTENT[selection.intent],
                            "arguments": {},
                        }
                    ],
                    "reward_basis": ["DB"],
                },
            }
            self.splits["base"].append(selection.task_id)
            self.splits[selection.split].append(selection.task_id)

    def test_manifest_is_balanced_and_unique(self) -> None:
        self.assertEqual(len(self.manifest.tasks), 9)
        self.assertEqual(
            Counter(task.intent for task in self.manifest.tasks),
            Counter(
                {
                    RetailIntent.CANCEL: 3,
                    RetailIntent.RETURN: 3,
                    RetailIntent.EXCHANGE: 3,
                }
            ),
        )
        self.assertEqual(
            len({task.task_id for task in self.manifest.tasks}),
            len(self.manifest.tasks),
        )

    def test_subset_validation_accepts_matching_write_tools(self) -> None:
        report = validate_subset(
            self.manifest,
            self.tasks,
            self.splits,
            benchmark_version="test-version",
            official_root="test-root",
        )

        self.assertEqual(report.task_count, 9)
        self.assertEqual(report.counts_by_intent[RetailIntent.CANCEL], 3)

    def test_subset_validation_rejects_wrong_intent_label(self) -> None:
        tasks = copy.deepcopy(self.tasks)
        cancellation = next(
            task for task in self.manifest.tasks if task.intent is RetailIntent.CANCEL
        )
        tasks[cancellation.task_id]["evaluation_criteria"]["actions"][0]["name"] = (
            "return_delivered_order_items"
        )

        with self.assertRaisesRegex(ValueError, "exactly one cancel_pending_order"):
            validate_subset(
                self.manifest,
                tasks,
                self.splits,
                benchmark_version="test-version",
                official_root="test-root",
            )

    def test_downloaded_official_checkout_validates(self) -> None:
        try:
            root = locate_tau2_root()
        except FileNotFoundError:
            self.skipTest("official τ-bench checkout is not present")

        report = validate_official_subset(root)
        self.assertEqual(report.benchmark_version, "1.0.1")
        self.assertEqual(report.task_count, 9)


if __name__ == "__main__":
    unittest.main()

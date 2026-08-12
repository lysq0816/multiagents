"""Compare expected post-write state with before/after order snapshots."""

from __future__ import annotations

from after_sales_agents.review.models import (
    StateDifference,
    StateVerificationRequest,
    StateVerificationResult,
    StateVerificationStatus,
)


class PostExecutionVerifier:
    def verify(self, request: StateVerificationRequest) -> StateVerificationResult:
        differences: list[StateDifference] = []
        changed = False
        missing_snapshot = False
        integrity_error = False
        seen_order_ids: set[str] = set()
        for expected in request.authorization.expected_state_changes:
            if expected.order_id in seen_order_ids:
                integrity_error = True
                differences.append(
                    StateDifference(
                        path=f"orders.{expected.order_id}.expected_state_changes",
                        expected="one final state per order",
                        actual="multiple expected states",
                    )
                )
                continue
            seen_order_ids.add(expected.order_id)
            before = request.before_snapshots.get(expected.order_id)
            after = request.after_snapshots.get(expected.order_id)
            if before is None or after is None:
                missing_snapshot = True
                differences.append(
                    StateDifference(
                        path=f"orders.{expected.order_id}",
                        expected="before and after snapshots",
                        actual={"before": before, "after": after},
                    )
                )
                continue
            if before != after:
                changed = True
            self._compare(
                differences,
                f"orders.{expected.order_id}.status",
                expected.expected_status,
                after.get("status"),
            )
            for field, value in expected.expected_fields.items():
                self._compare(
                    differences,
                    f"orders.{expected.order_id}.{field}",
                    value,
                    after.get(field),
                )

            if before == after:
                differences.append(
                    StateDifference(
                        path=f"orders.{expected.order_id}.snapshot_change",
                        expected="different from before snapshot",
                        actual="unchanged",
                    )
                )

        if not differences:
            status = StateVerificationStatus.MATCHED
        elif not changed and not missing_snapshot and not integrity_error:
            status = StateVerificationStatus.NOT_EXECUTED
        else:
            status = StateVerificationStatus.MISMATCH
        return StateVerificationResult(
            verification_id=f"verification:{request.authorization.authorization_id}",
            authorization_id=request.authorization.authorization_id,
            status=status,
            differences=differences,
        )

    @staticmethod
    def _compare(
        differences: list[StateDifference],
        path: str,
        expected: object,
        actual: object,
    ) -> None:
        if actual != expected:
            differences.append(StateDifference(path=path, expected=expected, actual=actual))

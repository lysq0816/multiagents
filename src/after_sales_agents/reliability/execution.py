"""Single-use, idempotent writes against an isolated in-memory retail sandbox."""

from __future__ import annotations

import hashlib
import json
import threading
from copy import deepcopy
from typing import Any

from after_sales_agents.domain.models import ActionType
from after_sales_agents.reliability.models import (
    ExecutionStatus,
    SandboxExecutionRequest,
    SandboxExecutionResult,
)
from after_sales_agents.reliability.resilience import call_write_once
from after_sales_agents.review.models import (
    ExecutionAuthorization,
    StateVerificationRequest,
    StateVerificationStatus,
)
from after_sales_agents.review.verification import PostExecutionVerifier


class ExecutionGateError(ValueError):
    pass


class AuthorizationConsumed(ExecutionGateError):
    pass


class IdempotencyConflict(ExecutionGateError):
    pass


class SandboxRetailBackend:
    """A deliberately local backend; it has no network adapter or production credentials."""

    def __init__(
        self,
        snapshots: dict[str, dict[str, Any]],
        *,
        fail_on_write_number: int | None = None,
        corrupt_result: bool = False,
    ) -> None:
        self._snapshots = deepcopy(snapshots)
        self.fail_on_write_number = fail_on_write_number
        self.corrupt_result = corrupt_result
        self.write_calls = 0

    def snapshots(self, order_ids: list[str]) -> dict[str, dict[str, Any]]:
        missing = [order_id for order_id in order_ids if order_id not in self._snapshots]
        if missing:
            raise KeyError(f"unknown sandbox orders: {missing}")
        return {order_id: deepcopy(self._snapshots[order_id]) for order_id in order_ids}

    def replace(self, snapshots: dict[str, dict[str, Any]]) -> None:
        self._snapshots = deepcopy(snapshots)

    def write(self, action: Any) -> None:
        self.write_calls += 1
        if self.fail_on_write_number == self.write_calls:
            raise ConnectionError("injected sandbox write failure")
        order = self._snapshots[action.order_id]
        if action.action_type is ActionType.CANCEL_ORDER:
            order.update(status="cancelled", cancel_reason=action.arguments["reason"])
        elif action.action_type is ActionType.CREATE_RETURN:
            order.update(
                status="return requested",
                return_items=sorted(action.item_ids),
                return_payment_method_id=action.arguments["payment_method_id"],
            )
        elif action.action_type is ActionType.EXCHANGE_ITEMS:
            order.update(
                status="exchange requested",
                exchange_items=sorted(action.item_ids),
                exchange_new_items=sorted(action.target_item_ids),
                exchange_payment_method_id=action.arguments["payment_method_id"],
            )
        else:
            raise ExecutionGateError(f"unsupported write action: {action.action_type}")
        if self.corrupt_result:
            order["status"] = "corrupted sandbox result"


class AuthorizedSandboxExecutor:
    """Atomically reserve an authorization, write once, verify, and commit or roll back."""

    def __init__(
        self,
        approved_authorizations: list[ExecutionAuthorization],
        *,
        write_timeout_seconds: float = 2.0,
    ) -> None:
        self.write_timeout_seconds = write_timeout_seconds
        self._approved = {
            authorization.authorization_id: deepcopy(authorization)
            for authorization in approved_authorizations
        }
        if len(self._approved) != len(approved_authorizations):
            raise ValueError("approved authorization IDs must be unique")
        self._lock = threading.Lock()
        self._consumed: dict[str, str] = {}
        self._idempotency: dict[str, tuple[str, SandboxExecutionResult]] = {}

    def execute(
        self,
        authorization: ExecutionAuthorization,
        request: SandboxExecutionRequest,
        backend: SandboxRetailBackend,
    ) -> SandboxExecutionResult:
        fingerprint = self._fingerprint(authorization, request)
        with self._lock:
            replay = self._idempotency.get(request.idempotency_key)
            if replay:
                existing_fingerprint, result = replay
                if existing_fingerprint != fingerprint:
                    raise IdempotencyConflict("idempotency key is bound to another request")
                return result.model_copy(update={"replayed": True})
            self._validate(authorization, request)
            previous_key = self._consumed.get(authorization.authorization_id)
            if previous_key is not None:
                raise AuthorizationConsumed(
                    f"authorization was already consumed with idempotency key {previous_key}"
                )
            # Reservation and consumption happen before the first consequential attempt. A write
            # timeout/failure is ambiguous and must never be retried under another key.
            self._consumed[authorization.authorization_id] = request.idempotency_key

            order_ids = list(dict.fromkeys(a.order_id for a in authorization.approved_actions))
            before = backend.snapshots(order_ids)
            write_attempts = 0
            try:
                for action in authorization.approved_actions:
                    write_attempts += 1
                    call_write_once(
                        lambda action=action: backend.write(action),
                        timeout_seconds=self.write_timeout_seconds,
                    )
            except Exception as exc:  # noqa: BLE001 - the sandbox boundary must always roll back
                backend.replace(before)
                result = SandboxExecutionResult(
                    execution_id=f"execution:{authorization.authorization_id}",
                    authorization_id=authorization.authorization_id,
                    idempotency_key=request.idempotency_key,
                    status=ExecutionStatus.WRITE_FAILED,
                    committed=False,
                    write_attempts=write_attempts,
                    error=f"{type(exc).__name__}: {exc}",
                    after_snapshots=before,
                )
                self._idempotency[request.idempotency_key] = (fingerprint, result)
                return result

            tentative_after = backend.snapshots(order_ids)
            verification = PostExecutionVerifier().verify(
                StateVerificationRequest(
                    authorization=authorization,
                    before_snapshots=before,
                    after_snapshots=tentative_after,
                )
            )
            verified = verification.status is StateVerificationStatus.MATCHED
            if not verified:
                backend.replace(before)
            result = SandboxExecutionResult(
                execution_id=f"execution:{authorization.authorization_id}",
                authorization_id=authorization.authorization_id,
                idempotency_key=request.idempotency_key,
                status=(
                    ExecutionStatus.EXECUTED_AND_VERIFIED
                    if verified
                    else ExecutionStatus.VERIFICATION_FAILED
                ),
                committed=verified,
                write_attempts=write_attempts,
                verification=verification,
                after_snapshots=tentative_after,
            )
            self._idempotency[request.idempotency_key] = (fingerprint, result)
            return result

    def _validate(
        self,
        authorization: ExecutionAuthorization,
        request: SandboxExecutionRequest,
    ) -> None:
        registered = self._approved.get(authorization.authorization_id)
        if registered is None or registered.model_dump(mode="json") != authorization.model_dump(
            mode="json"
        ):
            raise ExecutionGateError(
                "authorization is absent from or differs from the trusted approval store"
            )
        if request.authorization_id != authorization.authorization_id:
            raise ExecutionGateError("request authorization_id does not match authorization")
        if request.expected_plan_digest != authorization.plan_digest:
            raise ExecutionGateError("plan digest does not match the approved plan")
        if not authorization.single_use or not authorization.authorizes_execution:
            raise ExecutionGateError("authorization is not executable")
        if authorization.write_executed:
            raise AuthorizationConsumed("authorization already records a write")

    @staticmethod
    def _fingerprint(
        authorization: ExecutionAuthorization,
        request: SandboxExecutionRequest,
    ) -> str:
        canonical = json.dumps(
            {
                "authorization": authorization.model_dump(mode="json"),
                "request": request.model_dump(mode="json"),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

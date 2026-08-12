"""Bounded timeout and retry helpers with a strict read-only retry rule."""

from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

from after_sales_agents.reliability.models import (
    AttemptRecord,
    OperationKind,
    ReadCallResult,
    RetryPolicy,
)


class OperationTimedOut(TimeoutError):
    pass


class ReadRetriesExhausted(RuntimeError):
    def __init__(self, attempts: list[AttemptRecord], cause: BaseException) -> None:
        super().__init__(f"read failed after {len(attempts)} attempts: {cause}")
        self.attempts = attempts
        self.__cause__ = cause


def call_once_with_timeout[T](
    operation: Callable[[], T],
    timeout_seconds: float,
    *,
    settle_after_timeout: bool = False,
) -> T:
    """Run one operation with a wall-clock deadline.

    Python threads cannot be forcefully killed. Callers must therefore pass operations that
    support cancellation or have their own socket/database deadlines in production adapters.
    """

    pool = ThreadPoolExecutor(max_workers=1)
    pool_closed = False
    future = pool.submit(operation)
    try:
        return future.result(timeout=timeout_seconds)
    except FutureTimeout as exc:
        future.cancel()
        if settle_after_timeout:
            # A running Python thread cannot be killed safely. Consequential operations must
            # become quiescent before their caller rolls back or releases an authorization.
            pool.shutdown(wait=True, cancel_futures=True)
            pool_closed = True
        raise OperationTimedOut(f"operation exceeded {timeout_seconds:.3f}s") from exc
    finally:
        if not pool_closed:
            pool.shutdown(wait=False, cancel_futures=True)


def call_read_with_retry[T](
    operation: Callable[[], T],
    *,
    policy: RetryPolicy | None = None,
    retryable: tuple[type[BaseException], ...] = (TimeoutError, ConnectionError),
) -> ReadCallResult:
    """Retry an idempotent read with bounded attempts and linear backoff."""

    active = policy or RetryPolicy()
    attempts: list[AttemptRecord] = []
    for number in range(1, active.max_attempts + 1):
        started = time.perf_counter()
        try:
            value = call_once_with_timeout(operation, active.timeout_seconds)
        except retryable as exc:
            attempts.append(
                AttemptRecord(
                    attempt=number,
                    elapsed_ms=(time.perf_counter() - started) * 1000,
                    outcome=type(exc).__name__,
                )
            )
            if number == active.max_attempts:
                raise ReadRetriesExhausted(attempts, exc) from exc
            if active.backoff_seconds:
                time.sleep(active.backoff_seconds * number)
        else:
            attempts.append(
                AttemptRecord(
                    attempt=number,
                    elapsed_ms=(time.perf_counter() - started) * 1000,
                    outcome="success",
                )
            )
            return ReadCallResult(value=value, attempts=attempts)
    raise AssertionError("retry loop must return or raise")


def retry_allowed(kind: OperationKind) -> bool:
    return kind is OperationKind.READ


def call_write_once[T](operation: Callable[[], T], *, timeout_seconds: float = 2.0) -> T:
    """Attempt one write and never return while a timed-out worker can still mutate state.

    Production adapters must also enforce their own socket/database deadline. Python cannot
    safely terminate an already-running worker thread, so after the caller-visible deadline this
    helper waits for that one attempt to settle before reporting ``OperationTimedOut``.
    """

    return call_once_with_timeout(
        operation,
        timeout_seconds,
        settle_after_timeout=True,
    )

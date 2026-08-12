"""Small immutable TTL cache for verified read facts only."""

from __future__ import annotations

import time
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class _Entry:
    value: Any
    expires_at: float


class ReadFactCache:
    def __init__(
        self,
        *,
        ttl_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("cache TTL must be positive")
        self.ttl_seconds = ttl_seconds
        self._clock = clock
        self._entries: dict[tuple[str, str], _Entry] = {}
        self.hits = 0
        self.misses = 0

    def get(self, namespace: str, key: str) -> Any | None:
        entry = self._entries.get((namespace, key))
        if entry is None or entry.expires_at <= self._clock():
            self._entries.pop((namespace, key), None)
            self.misses += 1
            return None
        self.hits += 1
        return deepcopy(entry.value)

    def put_read_fact(self, namespace: str, key: str, value: Any) -> None:
        if not namespace.startswith("read:"):
            raise ValueError("only read facts may be cached")
        self._entries[(namespace, key)] = _Entry(
            value=deepcopy(value),
            expires_at=self._clock() + self.ttl_seconds,
        )

    def invalidate(self, namespace: str, key: str) -> None:
        self._entries.pop((namespace, key), None)

    def invalidate_subject(self, key: str) -> None:
        for cache_key in [entry for entry in self._entries if entry[1] == key]:
            self._entries.pop(cache_key, None)

"""Deterministic communication trimming that preserves evidence-bearing messages."""

from __future__ import annotations

from after_sales_agents.reliability.models import CommunicationMessage, CommunicationTrimResult


def trim_messages(
    messages: list[CommunicationMessage],
    *,
    max_messages: int = 8,
    max_characters: int = 4000,
) -> CommunicationTrimResult:
    if max_messages < 1 or max_characters < 1:
        raise ValueError("communication limits must be positive")
    original_characters = sum(len(message.content) for message in messages)
    selected: list[CommunicationMessage] = []
    used = 0
    evidence = [m for m in messages if m.fact_ids or m.policy_clause_ids]
    recency = [m for m in reversed(messages) if m not in evidence]
    for message in [*evidence, *recency]:
        if message in selected or len(selected) >= max_messages:
            continue
        if used + len(message.content) > max_characters:
            continue
        selected.append(message)
        used += len(message.content)
    selected.sort(key=lambda message: messages.index(message))
    retained_ids = {message.message_id for message in selected}
    return CommunicationTrimResult(
        messages=selected,
        original_messages=len(messages),
        original_characters=original_characters,
        retained_characters=used,
        dropped_message_ids=[m.message_id for m in messages if m.message_id not in retained_ids],
    )

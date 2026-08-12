"""In-memory usage ledger with deterministic per-ticket cost summaries."""

from __future__ import annotations

from collections import defaultdict

from after_sales_agents.reliability.models import CallKind, TicketCostSummary, UsageEvent


class UsageLedger:
    def __init__(self) -> None:
        self._events: list[UsageEvent] = []

    @property
    def events(self) -> tuple[UsageEvent, ...]:
        return tuple(self._events)

    def record(self, event: UsageEvent) -> None:
        self._events.append(event)

    def summarize_by_ticket_type(self) -> list[TicketCostSummary]:
        groups: dict[str, list[UsageEvent]] = defaultdict(list)
        for event in self._events:
            groups[event.ticket_type].append(event)
        summaries = []
        for ticket_type, events in sorted(groups.items()):
            summaries.append(
                TicketCostSummary(
                    ticket_type=ticket_type,
                    cases=len({event.case_id for event in events}),
                    total_calls=len(events),
                    model_calls=sum(e.call_kind is CallKind.MODEL for e in events),
                    read_tool_calls=sum(e.call_kind is CallKind.READ_TOOL for e in events),
                    write_tool_calls=sum(e.call_kind is CallKind.WRITE_TOOL for e in events),
                    cache_hits=sum(e.call_kind is CallKind.CACHE_HIT for e in events),
                    retry_attempts=sum(max(0, e.attempts - 1) for e in events),
                    input_tokens=sum(e.input_tokens for e in events),
                    output_tokens=sum(e.output_tokens for e in events),
                    estimated_cost_usd=round(sum(e.estimated_cost_usd for e in events), 8),
                )
            )
        return summaries

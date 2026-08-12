"""Least-privilege tool access for specialist agents."""

from __future__ import annotations

from copy import deepcopy
from enum import StrEnum
from typing import Any

from after_sales_agents.agents.models import ToolCallRecord, ToolCallResult
from after_sales_agents.domain.models import AgentRole


class ToolName(StrEnum):
    GET_ORDER_DETAILS = "get_order_details"
    GET_PRODUCT_DETAILS = "get_product_details"
    POLICY_SEARCH = "policy_search"
    POLICY_ELIGIBILITY = "policy_eligibility"
    CANCEL_PENDING_ORDER = "cancel_pending_order"
    RETURN_DELIVERED_ORDER_ITEMS = "return_delivered_order_items"
    EXCHANGE_DELIVERED_ORDER_ITEMS = "exchange_delivered_order_items"

    @property
    def is_write(self) -> bool:
        return self in {
            ToolName.CANCEL_PENDING_ORDER,
            ToolName.RETURN_DELIVERED_ORDER_ITEMS,
            ToolName.EXCHANGE_DELIVERED_ORDER_ITEMS,
        }


TOOL_PERMISSIONS: dict[AgentRole, frozenset[ToolName]] = {
    AgentRole.ORDER_SPECIALIST: frozenset(
        {ToolName.GET_ORDER_DETAILS, ToolName.GET_PRODUCT_DETAILS}
    ),
    AgentRole.POLICY_SPECIALIST: frozenset({ToolName.POLICY_SEARCH, ToolName.POLICY_ELIGIBILITY}),
    AgentRole.PLANNER: frozenset(),
    AgentRole.AUDITOR: frozenset(),
}


class ToolPermissionDenied(PermissionError):
    def __init__(self, role: AgentRole, tool: ToolName) -> None:
        super().__init__(f"{role.value} is not allowed to call {tool.value}")
        self.role = role
        self.tool = tool


class ToolPermissionGuard:
    def allowed_tools(self, role: AgentRole) -> frozenset[ToolName]:
        return TOOL_PERMISSIONS.get(role, frozenset())

    def ensure_allowed(self, role: AgentRole, tool: ToolName) -> None:
        if tool not in self.allowed_tools(role):
            raise ToolPermissionDenied(role, tool)


class SnapshotRetailTools:
    """Read-only local backend used until the official tool adapter is wired on Day 4+."""

    def __init__(
        self,
        order_snapshot: dict[str, Any],
        product_snapshots: dict[str, dict[str, Any]] | None = None,
        guard: ToolPermissionGuard | None = None,
    ) -> None:
        order_id = str(order_snapshot.get("order_id") or "")
        if not order_id:
            raise ValueError("order snapshot requires order_id")
        self._orders = {order_id: deepcopy(order_snapshot)}
        self._products = deepcopy(product_snapshots or {})
        self.guard = guard or ToolPermissionGuard()
        self.call_records: list[ToolCallRecord] = []

    def call(
        self,
        role: AgentRole,
        tool: ToolName,
        arguments: dict[str, Any],
    ) -> ToolCallResult:
        self.guard.ensure_allowed(role, tool)
        call = ToolCallRecord(
            call_id=f"{tool.value}:call-{len(self.call_records) + 1}",
            actor=role,
            tool_name=tool.value,
            arguments=deepcopy(arguments),
        )

        if tool is ToolName.GET_ORDER_DETAILS:
            order_id = str(arguments.get("order_id") or "")
            if order_id not in self._orders:
                raise KeyError(f"unknown order: {order_id}")
            data = self._orders[order_id]
        elif tool is ToolName.GET_PRODUCT_DETAILS:
            product_id = str(arguments.get("product_id") or "")
            if product_id not in self._products:
                raise KeyError(f"unknown product: {product_id}")
            data = self._products[product_id]
        else:
            raise NotImplementedError(f"snapshot backend cannot execute {tool.value}")

        self.call_records.append(call)
        return ToolCallResult(call=call, data=deepcopy(data))

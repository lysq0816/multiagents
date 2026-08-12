"""Typed records for the deterministic Day 8 architecture experiment."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from after_sales_agents.benchmark.models import RetailIntent


class ExperimentArchitecture(StrEnum):
    """Architectures compared by the fixed experiment matrix."""

    SINGLE_AGENT = "single_agent"
    FIXED_MULTI_AGENT = "fixed_multi_agent"
    ROUTED_MULTI_AGENT = "routed_multi_agent"
    ROUTED_MULTI_AGENT_WITH_AUDIT = "routed_multi_agent_with_audit"


class TaskDifficulty(StrEnum):
    ROUTINE = "routine"
    COMPLEX = "complex"


class FaultType(StrEnum):
    """Deterministic fault or complexity injected into a task card."""

    MISSING_INFORMATION = "missing_information"
    POLICY_CONFLICT = "policy_conflict"
    INVENTORY_UNAVAILABLE = "inventory_unavailable"
    MULTIPLE_ORDERS = "multiple_orders"
    EVIDENCE_MISMATCH = "evidence_mismatch"
    ARGUMENT_MISMATCH = "argument_mismatch"
    DUPLICATE_ACTION = "duplicate_action"


class ExperimentOutcome(StrEnum):
    READY_FOR_APPROVAL = "ready_for_approval"
    NEEDS_CLARIFICATION = "needs_clarification"
    POLICY_REJECTED = "policy_rejected"
    HUMAN_HANDOFF = "human_handoff"


class ExperimentTask(BaseModel):
    """One synthetic, deterministic Retail scenario card."""

    task_id: str = Field(pattern=r"^[CRE][0-9]{2}$")
    intent: RetailIntent
    title: str = Field(min_length=1)
    difficulty: TaskDifficulty
    order_status: Literal["pending", "delivered", "cancelled"]
    facts_complete: bool
    policy_eligible: bool
    user_confirmed: bool
    faults: list[FaultType] = Field(default_factory=list)
    requires_money_movement: bool = False
    requires_inventory_movement: bool = False
    order_count: int = Field(default=1, ge=1, le=3)
    estimated_read_tool_calls: int = Field(ge=0, le=8)
    expected_outcome: ExperimentOutcome

    @model_validator(mode="after")
    def validate_ground_truth(self) -> ExperimentTask:
        if len(self.faults) != len(set(self.faults)):
            raise ValueError("task faults must be unique")
        missing = FaultType.MISSING_INFORMATION in self.faults
        if missing is self.facts_complete:
            raise ValueError("missing_information must exactly match incomplete facts")
        multiple = FaultType.MULTIPLE_ORDERS in self.faults
        if multiple is (self.order_count == 1):
            raise ValueError("multiple_orders must exactly match order_count greater than one")
        if self.expected_outcome is not expected_outcome_for(self):
            raise ValueError("expected_outcome does not match deterministic ground truth")
        return self


def expected_outcome_for(task: ExperimentTask) -> ExperimentOutcome:
    """Derive the task's expected safe disposition from its ground truth."""

    faults = set(task.faults)
    if FaultType.MISSING_INFORMATION in faults:
        return ExperimentOutcome.NEEDS_CLARIFICATION
    if (
        not task.policy_eligible
        or FaultType.POLICY_CONFLICT in faults
        or FaultType.INVENTORY_UNAVAILABLE in faults
    ):
        return ExperimentOutcome.POLICY_REJECTED
    if FaultType.DUPLICATE_ACTION in faults:
        return ExperimentOutcome.NEEDS_CLARIFICATION
    if faults & {FaultType.EVIDENCE_MISMATCH, FaultType.ARGUMENT_MISMATCH}:
        return ExperimentOutcome.HUMAN_HANDOFF
    return ExperimentOutcome.READY_FOR_APPROVAL


class ExperimentTaskManifest(BaseModel):
    """The balanced 30-task workload used for every architecture."""

    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    benchmark_kind: Literal["offline_deterministic_fault_injection"] = (
        "offline_deterministic_fault_injection"
    )
    description: str = Field(min_length=1)
    tasks: list[ExperimentTask] = Field(min_length=30, max_length=30)

    @model_validator(mode="after")
    def validate_balance(self) -> ExperimentTaskManifest:
        task_ids = [task.task_id for task in self.tasks]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("experiment task IDs must be unique")
        counts = Counter(task.intent for task in self.tasks)
        if counts != {intent: 10 for intent in RetailIntent}:
            raise ValueError("the matrix requires exactly ten tasks per intent")
        return self


class ExperimentRunResult(BaseModel):
    """One architecture/task/repetition result."""

    architecture: ExperimentArchitecture
    task_id: str
    intent: RetailIntent
    repetition: int = Field(ge=1)
    route: str = Field(min_length=1)
    actual_outcome: ExperimentOutcome
    expected_outcome: ExperimentOutcome
    successful: bool
    policy_violation_count: int = Field(ge=0)
    unauthorized_write_count: Literal[0] = 0
    human_handoff: bool
    agent_calls: int = Field(ge=0)
    tool_calls: int = Field(ge=0)
    model_calls: Literal[0] = 0
    latency_ms: float = Field(ge=0)
    latency_kind: Literal["deterministic_operation_budget_not_wall_clock"] = (
        "deterministic_operation_budget_not_wall_clock"
    )
    input_tokens: None = None
    output_tokens: None = None
    total_tokens: None = None
    model_cost_usd: None = None
    outcome_signature: str = Field(pattern=r"^[a-f0-9]{64}$")
    notes: list[str] = Field(default_factory=list)


class ExperimentMetrics(BaseModel):
    """Aggregate safety, quality, handoff, and resource metrics."""

    run_count: int = Field(ge=1)
    successful_runs: int = Field(ge=0)
    success_rate: float = Field(ge=0, le=1)
    final_state_accuracy: float = Field(ge=0, le=1)
    policy_violation_count: int = Field(ge=0)
    policy_violation_rate: float = Field(ge=0, le=1)
    unauthorized_write_count: int = Field(ge=0)
    human_handoff_count: int = Field(ge=0)
    human_handoff_rate: float = Field(ge=0, le=1)
    average_agent_calls: float = Field(ge=0)
    average_tool_calls: float = Field(ge=0)
    model_calls: Literal[0] = 0
    average_latency_ms: float = Field(ge=0)
    latency_kind: Literal["deterministic_operation_budget_not_wall_clock"] = (
        "deterministic_operation_budget_not_wall_clock"
    )
    input_tokens: None = None
    output_tokens: None = None
    total_tokens: None = None
    model_cost_usd: None = None
    consistent_task_count: int = Field(ge=0)
    consistency_rate: float = Field(ge=0, le=1)


class ArchitectureMetrics(BaseModel):
    architecture: ExperimentArchitecture
    overall: ExperimentMetrics
    by_intent: dict[RetailIntent, ExperimentMetrics]


class ExperimentReport(BaseModel):
    """Complete, reproducible Day 8 report including every repeated run."""

    experiment_id: Literal["day8_offline_architecture_matrix_v1"] = (
        "day8_offline_architecture_matrix_v1"
    )
    methodology: Literal["deterministic_control_flow_fault_injection"] = (
        "deterministic_control_flow_fault_injection"
    )
    offline: Literal[True] = True
    deterministic: Literal[True] = True
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    experiment_code_version: Literal["day8-v1"] = "day8-v1"
    real_write_operations: Literal[0] = 0
    task_count: Literal[30] = 30
    repetitions_per_task: int = Field(ge=3)
    architecture_count: Literal[4] = 4
    total_run_count: int = Field(ge=360)
    model_usage_note: str = Field(min_length=1)
    latency_note: str = Field(min_length=1)
    result_scope_note: str = Field(min_length=1)
    manifest_name: str = Field(min_length=1)
    metrics: list[ArchitectureMetrics] = Field(min_length=4, max_length=4)
    runs: list[ExperimentRunResult] = Field(min_length=360)
    caveats: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_matrix(self) -> ExperimentReport:
        expected_runs = self.task_count * self.repetitions_per_task * self.architecture_count
        if self.total_run_count != expected_runs or len(self.runs) != expected_runs:
            raise ValueError("report does not contain the complete experiment matrix")
        if {metric.architecture for metric in self.metrics} != set(ExperimentArchitecture):
            raise ValueError("report metrics must include all four architectures")
        return self

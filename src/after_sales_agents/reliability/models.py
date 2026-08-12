"""Typed reliability, security, execution, and observability records."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from after_sales_agents.domain.models import AgentRole
from after_sales_agents.review.models import StateVerificationResult


class OperationKind(StrEnum):
    READ = "read"
    WRITE = "write"


class RetryPolicy(BaseModel):
    timeout_seconds: float = Field(default=2.0, gt=0, le=30)
    max_attempts: int = Field(default=3, ge=1, le=5)
    backoff_seconds: float = Field(default=0.05, ge=0, le=2)


class AttemptRecord(BaseModel):
    attempt: int = Field(ge=1)
    elapsed_ms: float = Field(ge=0)
    outcome: str = Field(min_length=1)


class ReadCallResult(BaseModel):
    value: Any
    attempts: list[AttemptRecord] = Field(min_length=1)


class SecurityFinding(BaseModel):
    code: str = Field(min_length=1)
    description: str = Field(min_length=1)


class SecurityAssessment(BaseModel):
    accepted_as_instructions: bool = False
    findings: list[SecurityFinding] = Field(default_factory=list)
    safe_text: str = Field(min_length=1)

    @property
    def suspicious(self) -> bool:
        return bool(self.findings)


class SignedHandoff(BaseModel):
    sender: AgentRole
    recipient: AgentRole
    case_id: str = Field(min_length=1)
    payload: dict[str, Any]
    signature: str = Field(pattern=r"^[a-f0-9]{64}$")


class CommunicationMessage(BaseModel):
    message_id: str = Field(min_length=1)
    sender: AgentRole
    content: str = Field(min_length=1)
    fact_ids: list[str] = Field(default_factory=list)
    policy_clause_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CommunicationTrimResult(BaseModel):
    messages: list[CommunicationMessage]
    original_messages: int = Field(ge=0)
    original_characters: int = Field(ge=0)
    retained_characters: int = Field(ge=0)
    dropped_message_ids: list[str] = Field(default_factory=list)


class CallKind(StrEnum):
    MODEL = "model"
    READ_TOOL = "read_tool"
    WRITE_TOOL = "write_tool"
    CACHE_HIT = "cache_hit"


class UsageEvent(BaseModel):
    case_id: str = Field(min_length=1)
    ticket_type: str = Field(min_length=1)
    component: str = Field(min_length=1)
    call_kind: CallKind
    latency_ms: float = Field(default=0, ge=0)
    attempts: int = Field(default=1, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    estimated_cost_usd: float = Field(default=0, ge=0)


class TicketCostSummary(BaseModel):
    ticket_type: str
    cases: int = Field(ge=0)
    total_calls: int = Field(ge=0)
    model_calls: int = Field(ge=0)
    read_tool_calls: int = Field(ge=0)
    write_tool_calls: int = Field(ge=0)
    cache_hits: int = Field(ge=0)
    retry_attempts: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    estimated_cost_usd: float = Field(ge=0)


class ExecutionStatus(StrEnum):
    EXECUTED_AND_VERIFIED = "executed_and_verified"
    VERIFICATION_FAILED = "verification_failed"
    WRITE_FAILED = "write_failed"


class SandboxExecutionRequest(BaseModel):
    authorization_id: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=8, max_length=128)
    expected_plan_digest: str = Field(pattern=r"^[a-f0-9]{64}$")


class SandboxExecutionResult(BaseModel):
    execution_id: str = Field(min_length=1)
    authorization_id: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    status: ExecutionStatus
    replayed: bool = False
    sandbox_only: Literal[True] = True
    committed: bool
    write_attempts: int = Field(ge=0)
    verification: StateVerificationResult | None = None
    error: str | None = None
    after_snapshots: dict[str, dict[str, Any]]

    @model_validator(mode="after")
    def require_verified_commit(self) -> SandboxExecutionResult:
        verified = self.status is ExecutionStatus.EXECUTED_AND_VERIFIED
        if self.committed is not verified:
            raise ValueError("only verified sandbox executions may commit")
        if self.status is ExecutionStatus.WRITE_FAILED and self.verification is not None:
            raise ValueError("a failed write cannot have post-write verification")
        if self.status is not ExecutionStatus.WRITE_FAILED and self.verification is None:
            raise ValueError("completed writes require post-write verification")
        return self

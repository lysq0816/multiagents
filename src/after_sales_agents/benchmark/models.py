"""Typed models for the fixed Retail benchmark subset and its reports."""

from __future__ import annotations

from collections import Counter
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class RetailIntent(StrEnum):
    """The three after-sales intents included in the MVP."""

    CANCEL = "cancel"
    RETURN = "return"
    EXCHANGE = "exchange"


class RetailTaskSelection(BaseModel):
    """One official τ-bench task selected for the fixed Day 2 subset."""

    task_id: str = Field(min_length=1)
    intent: RetailIntent
    split: Literal["train", "test"]
    note: str = Field(min_length=1)


class TaskSubsetManifest(BaseModel):
    """A stable task manifest used by every baseline variant."""

    name: str = Field(min_length=1)
    source: str = Field(min_length=1)
    selection_policy: str = Field(min_length=1)
    tasks: list[RetailTaskSelection] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_balance_and_uniqueness(self) -> TaskSubsetManifest:
        task_ids = [task.task_id for task in self.tasks]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("task IDs must be unique")

        counts = Counter(task.intent for task in self.tasks)
        expected = {intent: 3 for intent in RetailIntent}
        if counts != expected:
            raise ValueError("the Day 2 subset must contain exactly three tasks per intent")
        return self


class OfficialTaskSummary(BaseModel):
    """Validated metadata copied from the official task files."""

    task_id: str
    intent: RetailIntent
    split: Literal["train", "test"]
    reason_for_call: str
    known_info: str | None = None
    action_names: list[str]
    reward_basis: list[str]


class SubsetValidationReport(BaseModel):
    """Result of validating the fixed manifest against an official checkout."""

    benchmark: str = "tau2"
    benchmark_version: str
    domain: str = "retail"
    manifest_name: str
    official_root: str
    task_count: int
    counts_by_intent: dict[RetailIntent, int]
    tasks: list[OfficialTaskSummary]

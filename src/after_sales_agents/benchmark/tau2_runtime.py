"""Runtime profiles for launching the official τ2 agent without prompt leakage."""

from __future__ import annotations

import os

OFFICIAL_AGENT_INSTRUCTION_PROFILE = "official_tau2"
AUDITABLE_AGENT_INSTRUCTION_PROFILE = "auditable_money_calculation_v1"
AUDITABLE_AGENT_INSTRUCTION_SUFFIX = (
    "Whenever you need to calculate, add, subtract, compare, or total monetary "
    "amounts, you MUST call the calculate tool with the full arithmetic expression "
    "before stating the result. Never perform monetary arithmetic mentally."
)
AGENT_INSTRUCTION_PROFILES = {
    OFFICIAL_AGENT_INSTRUCTION_PROFILE: None,
    AUDITABLE_AGENT_INSTRUCTION_PROFILE: AUDITABLE_AGENT_INSTRUCTION_SUFFIX,
}


def build_subprocess_environment(
    *,
    evaluator_model: str,
    agent_instruction_profile: str,
    base_environment: dict[str, str] | None = None,
) -> dict[str, str]:
    """Build an isolated child environment for an official or diagnostic run."""

    environment = dict(base_environment if base_environment is not None else os.environ)
    environment["PYTHONUTF8"] = "1"
    environment["TAU2_NL_ASSERTIONS_MODEL"] = evaluator_model
    environment.pop("TAU2_AGENT_INSTRUCTION_SUFFIX", None)
    instruction_suffix = AGENT_INSTRUCTION_PROFILES[agent_instruction_profile]
    if instruction_suffix:
        environment["TAU2_AGENT_INSTRUCTION_SUFFIX"] = instruction_suffix
    return environment

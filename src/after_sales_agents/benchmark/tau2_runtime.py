"""Runtime profiles for launching the official τ2 agent without prompt leakage."""

from __future__ import annotations

import os

OFFICIAL_AGENT_INSTRUCTION_PROFILE = "official_tau2"
AUDITABLE_AGENT_INSTRUCTION_PROFILE = "auditable_money_calculation_v1"
OFFICIAL_AGENT_IMPLEMENTATION = "llm_agent"
MULTI_AGENT_IMPLEMENTATION = "after_sales_multiagent"
DEEPSEEK_REASONING_REPLAY_ENV = "TAU2_DEEPSEEK_REASONING_REPLAY"
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
    agent_implementation: str = OFFICIAL_AGENT_IMPLEMENTATION,
    agent_model: str | None = None,
    user_model: str | None = None,
    base_environment: dict[str, str] | None = None,
) -> dict[str, str]:
    """Build an isolated child environment for an official or diagnostic run."""

    environment = dict(base_environment if base_environment is not None else os.environ)
    environment["PYTHONUTF8"] = "1"
    environment["TAU2_NL_ASSERTIONS_MODEL"] = evaluator_model
    environment.pop("TAU2_AGENT_INSTRUCTION_SUFFIX", None)
    environment.pop("TAU2_AFTER_SALES_AGENT", None)
    environment.pop(DEEPSEEK_REASONING_REPLAY_ENV, None)
    instruction_suffix = AGENT_INSTRUCTION_PROFILES[agent_instruction_profile]
    if instruction_suffix:
        environment["TAU2_AGENT_INSTRUCTION_SUFFIX"] = instruction_suffix
    if agent_implementation == MULTI_AGENT_IMPLEMENTATION:
        environment["TAU2_AFTER_SALES_AGENT"] = MULTI_AGENT_IMPLEMENTATION
    if any(
        isinstance(model, str) and model.lower().startswith("deepseek/")
        for model in (agent_model, user_model)
    ):
        environment[DEEPSEEK_REASONING_REPLAY_ENV] = "1"
    return environment


def extract_reasoning_content(raw_data: object) -> str | None:
    """Extract DeepSeek thinking content retained by tau2's raw LiteLLM response."""

    if not isinstance(raw_data, dict):
        return None
    choices = raw_data.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return None
    message = choices[0].get("message")
    if not isinstance(message, dict):
        return None
    reasoning_content = message.get("reasoning_content")
    if not isinstance(reasoning_content, str) or not reasoning_content:
        provider_fields = message.get("provider_specific_fields")
        reasoning_content = (
            provider_fields.get("reasoning_content") if isinstance(provider_fields, dict) else None
        )
    return reasoning_content if isinstance(reasoning_content, str) and reasoning_content else None

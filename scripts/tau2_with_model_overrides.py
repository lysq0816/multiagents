"""Run the official τ2 CLI with environment-scoped evaluator and prompt overrides."""

from __future__ import annotations

import os


def apply_model_overrides() -> str | None:
    evaluator_model = os.getenv("TAU2_NL_ASSERTIONS_MODEL")
    if evaluator_model:
        import tau2.config as tau2_config
        import tau2.evaluator.evaluator_nl_assertions as nl_evaluator

        tau2_config.DEFAULT_LLM_NL_ASSERTIONS = evaluator_model
        tau2_config.DEFAULT_LLM_NL_ASSERTIONS_ARGS = {
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
        }
        nl_evaluator.DEFAULT_LLM_NL_ASSERTIONS = evaluator_model
        nl_evaluator.DEFAULT_LLM_NL_ASSERTIONS_ARGS = tau2_config.DEFAULT_LLM_NL_ASSERTIONS_ARGS
    return evaluator_model


def apply_agent_instruction_override() -> bool:
    """Append a local instruction without modifying the official τ2 checkout."""

    instruction_suffix = os.getenv("TAU2_AGENT_INSTRUCTION_SUFFIX", "").strip()
    if not instruction_suffix:
        return False

    from tau2.agent import llm_agent

    if instruction_suffix not in llm_agent.AGENT_INSTRUCTION:
        llm_agent.AGENT_INSTRUCTION = f"{llm_agent.AGENT_INSTRUCTION}\n\n{instruction_suffix}"
    return True


def main() -> int:
    apply_model_overrides()
    apply_agent_instruction_override()

    from tau2.cli import main as tau2_main

    result = tau2_main()
    return result if isinstance(result, int) else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Run the official τ2 CLI with environment-scoped evaluator and prompt overrides."""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from after_sales_agents.benchmark.tau2_runtime import (
    DEEPSEEK_REASONING_REPLAY_ENV,
    extract_reasoning_content,
)


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


def apply_custom_agent_registration() -> str | None:
    """Register the project agent in memory without editing the tau2 checkout."""

    agent_name = os.getenv("TAU2_AFTER_SALES_AGENT")
    if not agent_name:
        return None
    if agent_name != "after_sales_multiagent":
        raise ValueError(f"Unsupported project tau2 agent: {agent_name}")

    from after_sales_agents.benchmark.tau2_multiagent_runtime import (
        register_after_sales_multiagent,
    )

    return register_after_sales_multiagent()


def apply_deepseek_reasoning_replay() -> bool:
    """Preserve reasoning_content across DeepSeek thinking-mode tool turns."""

    if os.getenv(DEEPSEEK_REASONING_REPLAY_ENV) != "1":
        return False

    from tau2.data_model.message import (
        AssistantMessage,
        SystemMessage,
        ToolMessage,
        UserMessage,
    )
    from tau2.utils import llm_utils

    original = llm_utils.to_litellm_messages
    if getattr(original, "_after_sales_reasoning_replay", False):
        return False

    def to_litellm_messages_with_reasoning(messages):
        converted = original(messages)
        compatible_messages = [
            message
            for message in messages
            if isinstance(message, (UserMessage, AssistantMessage, ToolMessage, SystemMessage))
        ]
        for source, target in zip(compatible_messages, converted, strict=True):
            if not isinstance(source, AssistantMessage) or not source.is_tool_call():
                continue
            reasoning_content = extract_reasoning_content(source.raw_data)
            if reasoning_content:
                target["reasoning_content"] = reasoning_content
        return converted

    to_litellm_messages_with_reasoning._after_sales_reasoning_replay = True
    llm_utils.to_litellm_messages = to_litellm_messages_with_reasoning
    return True


def main() -> int:
    apply_model_overrides()
    apply_agent_instruction_override()
    apply_custom_agent_registration()
    apply_deepseek_reasoning_replay()

    from tau2.cli import main as tau2_main

    result = tau2_main()
    return result if isinstance(result, int) else 0


if __name__ == "__main__":
    raise SystemExit(main())

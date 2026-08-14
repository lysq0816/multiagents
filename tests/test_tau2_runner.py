from after_sales_agents.benchmark.tau2_runtime import (
    AUDITABLE_AGENT_INSTRUCTION_PROFILE,
    DEEPSEEK_REASONING_REPLAY_ENV,
    MULTI_AGENT_IMPLEMENTATION,
    OFFICIAL_AGENT_INSTRUCTION_PROFILE,
    build_subprocess_environment,
    extract_reasoning_content,
)


def test_official_profile_removes_any_inherited_prompt_override() -> None:
    environment = build_subprocess_environment(
        evaluator_model="deepseek/test-model",
        agent_instruction_profile=OFFICIAL_AGENT_INSTRUCTION_PROFILE,
        base_environment={"TAU2_AGENT_INSTRUCTION_SUFFIX": "stale override"},
    )

    assert "TAU2_AGENT_INSTRUCTION_SUFFIX" not in environment
    assert "TAU2_AFTER_SALES_AGENT" not in environment
    assert environment["TAU2_NL_ASSERTIONS_MODEL"] == "deepseek/test-model"


def test_auditable_profile_is_explicitly_opt_in() -> None:
    environment = build_subprocess_environment(
        evaluator_model="deepseek/test-model",
        agent_instruction_profile=AUDITABLE_AGENT_INSTRUCTION_PROFILE,
        base_environment={},
    )

    assert "MUST call the calculate tool" in environment["TAU2_AGENT_INSTRUCTION_SUFFIX"]


def test_multi_agent_registration_is_explicitly_forwarded() -> None:
    environment = build_subprocess_environment(
        evaluator_model="deepseek/test-model",
        agent_instruction_profile=OFFICIAL_AGENT_INSTRUCTION_PROFILE,
        agent_implementation=MULTI_AGENT_IMPLEMENTATION,
        base_environment={},
    )

    assert environment["TAU2_AFTER_SALES_AGENT"] == MULTI_AGENT_IMPLEMENTATION


def test_deepseek_runs_enable_reasoning_content_replay_without_inheriting_it() -> None:
    environment = build_subprocess_environment(
        evaluator_model="deepseek/judge",
        agent_instruction_profile=OFFICIAL_AGENT_INSTRUCTION_PROFILE,
        agent_model="deepseek/deepseek-v4-flash",
        user_model="deepseek/deepseek-v4-flash",
        base_environment={DEEPSEEK_REASONING_REPLAY_ENV: "stale"},
    )

    assert environment[DEEPSEEK_REASONING_REPLAY_ENV] == "1"

    non_deepseek = build_subprocess_environment(
        evaluator_model="openai/judge",
        agent_instruction_profile=OFFICIAL_AGENT_INSTRUCTION_PROFILE,
        agent_model="openai/test",
        user_model="openai/test",
        base_environment={DEEPSEEK_REASONING_REPLAY_ENV: "stale"},
    )
    assert DEEPSEEK_REASONING_REPLAY_ENV not in non_deepseek


def test_reasoning_content_is_extracted_from_litellm_raw_response() -> None:
    raw_data = {
        "choices": [
            {
                "message": {
                    "content": "",
                    "reasoning_content": "retain this tool-call reasoning",
                }
            }
        ]
    }

    assert extract_reasoning_content(raw_data) == "retain this tool-call reasoning"
    assert extract_reasoning_content({"choices": []}) is None

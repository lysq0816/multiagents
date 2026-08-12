from after_sales_agents.benchmark.tau2_runtime import (
    AUDITABLE_AGENT_INSTRUCTION_PROFILE,
    OFFICIAL_AGENT_INSTRUCTION_PROFILE,
    build_subprocess_environment,
)


def test_official_profile_removes_any_inherited_prompt_override() -> None:
    environment = build_subprocess_environment(
        evaluator_model="deepseek/test-model",
        agent_instruction_profile=OFFICIAL_AGENT_INSTRUCTION_PROFILE,
        base_environment={"TAU2_AGENT_INSTRUCTION_SUFFIX": "stale override"},
    )

    assert "TAU2_AGENT_INSTRUCTION_SUFFIX" not in environment
    assert environment["TAU2_NL_ASSERTIONS_MODEL"] == "deepseek/test-model"


def test_auditable_profile_is_explicitly_opt_in() -> None:
    environment = build_subprocess_environment(
        evaluator_model="deepseek/test-model",
        agent_instruction_profile=AUDITABLE_AGENT_INSTRUCTION_PROFILE,
        base_environment={},
    )

    assert "MUST call the calculate tool" in environment["TAU2_AGENT_INSTRUCTION_SUFFIX"]

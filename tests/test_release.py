import tomllib
from pathlib import Path

from after_sales_agents.api import app

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_container_delivery_files_exist_and_exclude_secrets() -> None:
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")
    compose = (PROJECT_ROOT / "compose.yaml").read_text(encoding="utf-8")
    dockerignore = (PROJECT_ROOT / ".dockerignore").read_text(encoding="utf-8")

    assert "local_secrets.py" not in dockerfile
    assert "OPENAI_API_KEY" not in compose
    assert "DEEPSEEK_API_KEY" not in compose
    assert "src/after_sales_agents/local_secrets.py" in dockerignore
    assert "artifacts" in dockerignore


def test_release_openapi_keeps_all_completed_workflow_paths() -> None:
    paths = app.openapi()["paths"]

    assert {
        "/health",
        "/api/v1/routing/preview",
        "/api/v1/policy/search",
        "/api/v1/policy/eligibility",
        "/api/v1/collaboration/review",
        "/api/v1/planning/review",
        "/api/v1/review/audit",
        "/api/v1/review/decision",
        "/api/v1/review/verify-state",
    }.issubset(paths)


def test_release_contains_ui_experiment_reliability_and_demo_assets() -> None:
    required = [
        "src/after_sales_agents/ui/index.html",
        "src/after_sales_agents/reliability/execution.py",
        "benchmarks/retail_day8_tasks.json",
        "artifacts/day8/experiment_report.json",
        "scripts/run_day8_experiment.py",
        "scripts/run_day9_reliability_demo.py",
        "scripts/run_delivery_scenarios.py",
    ]

    assert all((PROJECT_ROOT / path).is_file() for path in required)


def test_wheel_configuration_includes_the_runtime_policy_catalog() -> None:
    configuration = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    force_include = configuration["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]

    assert force_include == {
        "policies/retail_policy_clauses.json": (
            "after_sales_agents/policy/retail_policy_clauses.json"
        )
    }

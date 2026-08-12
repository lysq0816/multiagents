"""Load model credentials from environment variables or local-only code."""

from __future__ import annotations

import importlib
import os
import sys

KNOWN_MODEL_KEYS = (
    "OPENAI_API_KEY",
    "DEEPSEEK_API_KEY",
    "ANTHROPIC_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "OPENROUTER_API_KEY",
)


def load_model_credentials(
    module_name: str = "after_sales_agents.local_secrets",
) -> list[str]:
    """Load non-empty local credentials without overriding the environment."""

    previous_dont_write_bytecode = sys.dont_write_bytecode
    try:
        # Secret-bearing source must never be copied into a recoverable __pycache__ artifact.
        # The setting is restored immediately after this one-shot local import.
        sys.dont_write_bytecode = True
        try:
            local_secrets = importlib.import_module(module_name)
        except ModuleNotFoundError as error:
            if error.name != module_name:
                raise
            local_secrets = None
    finally:
        sys.dont_write_bytecode = previous_dont_write_bytecode

    if local_secrets is not None:
        provider = str(getattr(local_secrets, "MODEL_PROVIDER", "")).lower()
        for name in KNOWN_MODEL_KEYS:
            if provider == "deepseek" and name == "OPENAI_API_KEY":
                continue
            value = getattr(local_secrets, name, "")
            if isinstance(value, str) and value.strip():
                os.environ.setdefault(name, value.strip())

        if provider == "deepseek" and not os.getenv("DEEPSEEK_API_KEY"):
            legacy_value = getattr(local_secrets, "OPENAI_API_KEY", "")
            if isinstance(legacy_value, str) and legacy_value.strip():
                os.environ["DEEPSEEK_API_KEY"] = legacy_value.strip()

    return [name for name in KNOWN_MODEL_KEYS if os.getenv(name)]

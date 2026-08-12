from __future__ import annotations

import os
import sys
from types import ModuleType

from after_sales_agents.model_credentials import load_model_credentials


def test_load_model_credentials_from_local_module(monkeypatch) -> None:
    module_name = "test_local_model_secrets"
    local_module = ModuleType(module_name)
    local_module.OPENAI_API_KEY = "test-local-key"
    monkeypatch.setitem(sys.modules, module_name, local_module)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    configured = load_model_credentials(module_name)

    assert "OPENAI_API_KEY" in configured
    assert os.environ["OPENAI_API_KEY"] == "test-local-key"


def test_environment_value_takes_precedence(monkeypatch) -> None:
    module_name = "test_local_model_secrets_precedence"
    local_module = ModuleType(module_name)
    local_module.OPENAI_API_KEY = "test-local-key"
    monkeypatch.setitem(sys.modules, module_name, local_module)
    monkeypatch.setenv("OPENAI_API_KEY", "test-environment-key")

    load_model_credentials(module_name)

    assert os.environ["OPENAI_API_KEY"] == "test-environment-key"


def test_deepseek_provider_maps_existing_local_slot(monkeypatch) -> None:
    module_name = "test_local_deepseek_secrets"
    local_module = ModuleType(module_name)
    local_module.MODEL_PROVIDER = "deepseek"
    local_module.OPENAI_API_KEY = "test-deepseek-key"
    monkeypatch.setitem(sys.modules, module_name, local_module)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    configured = load_model_credentials(module_name)

    assert "DEEPSEEK_API_KEY" in configured
    assert "OPENAI_API_KEY" not in configured
    assert os.environ["DEEPSEEK_API_KEY"] == "test-deepseek-key"


def test_secret_module_import_never_creates_bytecode(tmp_path, monkeypatch) -> None:
    module_name = "ephemeral_local_credentials"
    module_path = tmp_path / f"{module_name}.py"
    module_path.write_text('OPENAI_API_KEY = "test-no-bytecode-key"\n', encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    configured = load_model_credentials(module_name)

    assert "OPENAI_API_KEY" in configured
    assert not list(tmp_path.rglob(f"{module_name}*.pyc"))
    sys.modules.pop(module_name, None)

"""Builds the chat model chain from llm.toml at startup (spec 5.5).

A bad config stops the app. Chain entries whose API key is missing are left out, so a local
setup with only a Gemini key still works; with no usable entry there is no chat model and
sending a message answers 501.
"""

import logging
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Final

from cardwise_api.settings import Settings
from cardwise_llm import (
    ChatModel,
    InMemoryQuotaStore,
    LLMConfig,
    LLMConfigError,
    build_chat_model,
    load_llm_config,
)

log: Final = logging.getLogger("cardwise_api.llm")

CONFIG_NAME: Final = "llm.toml"
REPO_CONFIG: Final = Path(__file__).resolve().parents[2] / CONFIG_NAME
"""api/llm.toml when running from the repository (src layout)."""


def config_path(settings: Settings) -> Path | None:
    if settings.llm_config is not None:
        return settings.llm_config
    for candidate in (REPO_CONFIG, Path.cwd() / CONFIG_NAME):
        if candidate.is_file():
            return candidate
    return None


def build_model(
    settings: Settings, *, environ: Mapping[str, str] | None = None
) -> ChatModel | None:
    path = config_path(settings)
    if path is None:
        if settings.deployed:
            raise LLMConfigError(f"{CONFIG_NAME} not found; set CARDWISE_LLM_CONFIG")
        log.warning("no %s found: chat is unavailable", CONFIG_NAME)
        return None
    config = load_llm_config(path)
    env = {**(os.environ if environ is None else environ), **settings.llm_keys}
    usable = tuple(entry for entry in config.chain if env.get(entry.key_env, "").strip())
    left_out = [entry.display_name for entry in config.chain if entry not in usable]
    if left_out:
        log.warning(
            "models without an API key left out of the chain",
            extra={"fields": {"models": left_out}},
        )
    if not usable:
        log.warning("no model in %s has an API key: chat is unavailable", path.name)
        return None
    # One process-local quota store. Serverless instances do not share it; a Postgres store
    # (see cardwise_llm.quota) would make caps global.
    return build_chat_model(
        LLMConfig(policy=config.policy, chain=usable), env=env, quota=InMemoryQuotaStore()
    )

from pathlib import Path

import pytest

from cardwise_llm import LLMConfigError, build_chat_model, load_llm_config

APP_CONFIG = Path(__file__).parents[3] / "api" / "llm.toml"
KEYS = {"CARDWISE_GEMINI_API_KEY": "g-test", "CARDWISE_OPENROUTER_API_KEY": "or-test"}


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "llm.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_app_config_parses_and_builds_in_order() -> None:
    config = load_llm_config(APP_CONFIG)
    model = build_chat_model(config, env=KEYS)

    assert model.models == tuple(entry.display_name for entry in config.chain)
    assert model.models[0].startswith("gemini:")
    assert any(name.startswith("openrouter:") for name in model.models)


def test_openai_compat_entry_builds_with_its_own_key(tmp_path: Path) -> None:
    config = load_llm_config(
        write(
            tmp_path,
            """
[[chain]]
provider = "openai_compat"
label = "groq"
model = "llama-test"
base_url = "https://example.invalid/v1"
api_key_env = "CARDWISE_GROQ_API_KEY"
daily_request_cap = 10
""",
        )
    )
    assert config.chain[0].limits.requests_per_day == 10
    model = build_chat_model(config, env={"CARDWISE_GROQ_API_KEY": "k"})
    assert model.models == ("groq:llama-test",)


def test_missing_key_names_the_variable_not_the_value() -> None:
    config = load_llm_config(APP_CONFIG)
    with pytest.raises(LLMConfigError) as raised:
        build_chat_model(
            config, env={"CARDWISE_GEMINI_API_KEY": "g-test", "CARDWISE_OPENROUTER_API_KEY": " "}
        )
    message = str(raised.value)
    assert "CARDWISE_OPENROUTER_API_KEY" in message
    assert "CARDWISE_GEMINI_API_KEY" not in message
    assert "g-test" not in message


ENTRY = '[[chain]]\nprovider = "gemini"\nmodel = "gemini-test"\n'


@pytest.mark.parametrize(
    ("text", "complaint"),
    [
        ("[policy]\nmax_attempts = 2\n", "chain"),
        ("chain = []\n", "chain"),
        ('[[chain]]\nprovider = "anthropic"\nmodel = "x"\n', "provider"),
        ('[[chain]]\nprovider = "openai_compat"\nmodel = "x"\n', "base_url"),
        (ENTRY + 'base_url = "https://example.invalid"\n', "only for openai_compat"),
        (ENTRY + ENTRY, "more than once"),
        (ENTRY + 'day_resets_in = "Mars/Base"\n', "unknown time zone"),
        (ENTRY + "daily_request_cap = 0\n", "daily_request_cap"),
        (ENTRY + "timeout_s = 600\n", "timeout_s"),
        (ENTRY + 'api_key = "sk-oops"\n', "api_key"),
        (ENTRY + 'api_key_env = "HOME"\n', "api_key_env"),
        ('[[chain]]\nprovider = "gemini"\nmodel = "two words"\n', "model"),
        ("[policy]\nmax_attempts = 9\n" + ENTRY, "max_attempts"),
        ("[[chain]\n", "llm.toml"),
    ],
)
def test_invalid_config_fails_with_a_clear_message(
    tmp_path: Path, text: str, complaint: str
) -> None:
    with pytest.raises(LLMConfigError, match=complaint) as raised:
        load_llm_config(write(tmp_path, text))
    assert "sk-oops" not in str(raised.value)


def test_missing_file_is_a_config_error(tmp_path: Path) -> None:
    with pytest.raises(LLMConfigError):
        load_llm_config(tmp_path / "nope.toml")

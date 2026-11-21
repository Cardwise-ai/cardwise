from collections.abc import Callable
from typing import Any
from uuid import uuid4

import pytest

from cardwise_api.chat_model import REPO_CONFIG, build_model
from cardwise_api.fake_backend import FakeCardBackend, hit
from cardwise_api.testing import Harness, make_settings
from cardwise_llm import LLMConfigError

HarnessFactory = Callable[..., Harness]

SOL_RING = hit("Sol Ring", type_line="Artifact", text="{T}: Add {C}{C}.")
SOL_TALISMAN = hit("Sol Talisman", type_line="Artifact", text="Suspend 3")
CULTIVATE = hit("Cultivate", type_line="Sorcery")


@pytest.fixture
def cards(new_harness: HarnessFactory) -> Harness:
    return new_harness(backend=FakeCardBackend([SOL_RING, SOL_TALISMAN, CULTIVATE]))


def get(harness: Harness, path: str, **params: Any) -> Any:
    return harness.client.get(path, params=params, headers=harness.headers)


def test_search_returns_summaries(cards: Harness) -> None:
    response = get(cards, "/v1/cards/search", q="sol", limit=1)
    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "oracle_id": str(SOL_RING.oracle_id),
                "name": "Sol Ring",
                "mana_cost": "{1}",
                "type_line": "Artifact",
                "image_uri": SOL_RING.image_uri,
            }
        ]
    }


@pytest.mark.parametrize("params", [{"q": ""}, {"q": "sol", "limit": 51}, {}])
def test_search_rejects_bad_queries(cards: Harness, params: dict[str, Any]) -> None:
    assert get(cards, "/v1/cards/search", **params).status_code == 422


def test_card_detail_and_unknown_card(cards: Harness) -> None:
    response = get(cards, f"/v1/cards/{CULTIVATE.oracle_id}")
    assert response.status_code == 200
    assert response.json()["name"] == "Cultivate"
    assert get(cards, f"/v1/cards/{uuid4()}").status_code == 404


def test_card_endpoints_need_a_user(cards: Harness) -> None:
    response = cards.client.get("/v1/cards/search", params={"q": "sol"})
    assert response.status_code == 401


def test_without_a_database_card_endpoints_are_501(harness: Harness) -> None:
    assert get(harness, "/v1/cards/search", q="sol").status_code == 501


def test_models_without_a_key_are_left_out_of_the_chain() -> None:
    settings = make_settings(gemini_api_key="g-key", openrouter_api_key=None)
    model = build_model(settings, environ={})
    assert model is not None
    assert "gemini" in model.name
    assert "openrouter" not in model.name


def test_no_keys_means_no_chat_model() -> None:
    settings = make_settings(gemini_api_key=None, openrouter_api_key=None)
    assert build_model(settings, environ={}) is None


def test_a_bad_config_stops_the_app() -> None:
    bad = REPO_CONFIG.with_name("pyproject.toml")
    with pytest.raises(LLMConfigError):
        build_model(make_settings(llm_config=bad, gemini_api_key="g-key"), environ={})

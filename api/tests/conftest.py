from collections.abc import Callable, Iterator

import pytest

from cardwise_api.agent.port import Agent
from cardwise_api.settings import Settings
from cardwise_api.testing import (
    FakeJwks,
    Harness,
    ScriptedAgent,
    SigningKey,
    Tokens,
    ec_key,
    make_harness,
)


@pytest.fixture(scope="session")
def signing_key() -> SigningKey:
    return ec_key()


@pytest.fixture
def jwks(signing_key: SigningKey) -> FakeJwks:
    return FakeJwks([signing_key])


@pytest.fixture
def tokens(signing_key: SigningKey) -> Tokens:
    return Tokens(signing_key)


HarnessFactory = Callable[..., Harness]


@pytest.fixture
def new_harness(tokens: Tokens, jwks: FakeJwks) -> Iterator[HarnessFactory]:
    made: list[Harness] = []

    def make(*, agent: Agent | None = None, settings: Settings | None = None) -> Harness:
        harness = make_harness(tokens, jwks, agent=agent, settings=settings)
        made.append(harness)
        return harness

    yield make
    for harness in made:
        harness.client.close()


@pytest.fixture
def harness(new_harness: HarnessFactory) -> Harness:
    return new_harness(agent=ScriptedAgent())

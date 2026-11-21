from collections.abc import Callable
from uuid import UUID

import pytest

from cardwise_api.agent.grounding import Grounding, RefFilter
from cardwise_api.fake_backend import hit

SOL_RING = hit("Sol Ring", type_line="Artifact")
CULTIVATE = hit("Cultivate", type_line="Sorcery")
MDFC = hit("Agadeem's Awakening // Agadeem, the Undercrypt", type_line="Sorcery // Land")
UNSEEN = UUID("11111111-2222-3333-4444-555555555555")


def grounded(*deltas: str) -> tuple[str, Grounding]:
    grounding = Grounding()
    for card in (SOL_RING, CULTIVATE, MDFC):
        grounding.add(card)
    refs = RefFilter(grounding)
    text = "".join(refs.feed(d) for d in deltas) + refs.flush()
    return text, grounding


def chars(text: str) -> list[str]:
    return list(text)


def test_a_seen_card_stays_linked_with_our_name() -> None:
    text, grounding = grounded(f"Play [[{SOL_RING.oracle_id}|sol ring]] early.")
    assert text == f"Play [[{SOL_RING.oracle_id}|Sol Ring]] early."
    assert [c.name for c in grounding.cited] == ["Sol Ring"]


def test_an_unseen_id_is_unlinked_to_the_plain_name() -> None:
    text, grounding = grounded(f"Try [[{UNSEEN}|Mana Crypt]] too.")
    assert text == "Try Mana Crypt too."
    assert grounding.cited == []


def test_a_name_only_citation_links_a_seen_card_or_falls_back_to_text() -> None:
    text, grounding = grounded("[[cultivate]] and [[Kodama's Reach]]")
    assert text == f"[[{CULTIVATE.oracle_id}|Cultivate]] and Kodama's Reach"
    assert [c.name for c in grounding.cited] == ["Cultivate"]


def test_a_face_name_links_the_whole_card() -> None:
    text, _ = grounded("[[Agadeem, the Undercrypt]]")
    assert text == f"[[{MDFC.oracle_id}|{MDFC.name}]]"


@pytest.mark.parametrize("split", [chars, lambda t: [t[:9], t[9:30], t[30:]]])
def test_citations_split_across_deltas_are_handled(split: Callable[[str], list[str]]) -> None:
    source = f"A [[{SOL_RING.oracle_id}|Sol Ring]] and [[{UNSEEN}|Fake]] and [x]."
    text, _ = grounded(*split(source))
    assert text == f"A [[{SOL_RING.oracle_id}|Sol Ring]] and Fake and [x]."


def test_bare_unseen_ids_are_removed_even_when_split() -> None:
    source = f"id {UNSEEN} and {SOL_RING.oracle_id}."
    text, _ = grounded(*chars(source))
    assert text == f"id  and {SOL_RING.oracle_id}."


def test_cards_are_cited_once_in_order_of_first_citation() -> None:
    ids = (CULTIVATE.oracle_id, SOL_RING.oracle_id, CULTIVATE.oracle_id)
    text, grounding = grounded(*(f"[[{i}|x]] " for i in ids))
    assert [c.oracle_id for c in grounding.cited] == [CULTIVATE.oracle_id, SOL_RING.oracle_id]
    assert text.count("[[") == 3


def test_an_unfinished_citation_is_released_as_text() -> None:
    text, grounding = grounded("Look at [[Sol Ri")
    assert text == "Look at [[Sol Ri"
    assert grounding.cited == []


def test_brackets_that_are_not_citations_pass_through() -> None:
    text, _ = grounded("Costs {T}: add [C]. [[]] and [[a|b|c]]\nok")
    assert text == "Costs {T}: add [C]. [[]] and [[a|b|c]]\nok"

from cardwise_api.agent.prompt import build_system_prompt


def test_system_prompt_covers_conversation_context_grounding_and_explanations() -> None:
    prompt = " ".join(build_system_prompt().split())

    for instruction in (
        "Use the full conversation history in this request",
        "selected commander",
        "explicitly named or included cards",
        "colors/color identity",
        "strategy",
        "budget",
        "roles to fill",
        "exclusions",
        "ask one focused clarifying question",
        "color_identity_within",
        "legal_in set to commander",
        "pricing or availability",
        "speculative synergy idea",
        "never invent a card's capabilities",
        "returned by a tool while answering this message",
        "[[oracle_id|Card Name]]",
    ):
        assert instruction in prompt


def test_similar_card_recommendations_require_commander_legal_confirmation() -> None:
    prompt = " ".join(build_system_prompt().split())

    for instruction in (
        "Treat similar_cards as discovery only",
        "confirm it with search_cards",
        "candidate's exact name as text",
        "color_identity_within set to the commander's colors",
        "legal_in set to commander",
        "Recommend it only if that search returns the candidate",
        "otherwise, do not recommend it",
    ):
        assert instruction in prompt

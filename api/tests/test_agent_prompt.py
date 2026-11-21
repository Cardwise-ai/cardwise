from cardwise_api.agent.prompt import build_system_prompt


def test_system_prompt_covers_conversation_context_grounding_and_explanations() -> None:
    prompt = " ".join(build_system_prompt().split())

    for instruction in (
        "Use the full conversation history provided above",
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

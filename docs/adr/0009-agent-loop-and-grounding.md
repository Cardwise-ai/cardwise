# 0009: Our own agent loop with fixed caps and server-side citation grounding

Status: accepted
Date: 2026-11-24

## Context
Spec 7.4 gives the agent four tools over the card corpus and asks for hard limits per answer, so a free-tier model cannot loop or run past the serverless timeout. Answers link cards as `[[oracle_id|name]]`, and the web client turns those into card chips. A model can invent IDs or cite cards it never looked up. ADR 0003 keeps the tool loop on our side of the `ChatModel` port. The send route holds one asyncpg connection per request (ADR 0007).

## Decision
- `ChatAgent` (`cardwise_api.agent.loop`) runs the loop itself over `ChatModel.stream`: model turn, tool calls, results, repeat. Caps per answer are 4 tool rounds, 8 tool calls and a 60 s wall clock. Once a cap is reached, or less than 15 s remain, the next turn is offered no tools, and the last tool result carries an "answer now" note. A tool-call turn with no tools offered ends the loop. Running out of time raises `LLMError(TIMEOUT)`, so the reply is saved as failed with the text so far.
- Tool calls run one at a time on the request's connection. The card backend is built per request from that connection (`Services.backend_factory`).
- Tool results are compact text inside `<tool_result>`. Each card is written as the exact citation to copy, and list results clip rules text. An invalid call gets the validation error back once. A second invalid call ends tool use.
- Grounding runs on the stream (`RefFilter`). A citation whose ID a tool returned this turn is kept, with our card name. `[[Name]]` is linked if the name matches a returned card. Any other citation is unlinked to its plain name, and a bare UUID no tool returned is removed. The cards event lists the linked cards in order of first citation.
- The chain is built at startup from `api/llm.toml`. Entries without an API key are left out. With none left, there is no chat model, and sending a message answers 501.

## Consequences
- No invented card ID reaches the client or the database, at the cost of holding back a possible partial citation (at most about 200 characters) until it closes.
- Caps are per answer, and the quota store is per process. Instances do not share free-tier budgets until a Postgres `QuotaStore` exists.
- Revisit if tool calls need to run in parallel. That would need a connection pool per request or a backend that does not share the request connection.

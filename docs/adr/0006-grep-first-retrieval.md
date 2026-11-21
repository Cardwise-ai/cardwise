# 0006: Start with lexical retrieval, add embeddings later

Status: accepted
Date: 2026-11-21

## Context
Whether to use vector RAG or a grep-style lexical search over Scryfall and Tagger data is undecided. Lexical search over structured fields and tags is cheap, exact and easy to evaluate. Embeddings add a model dependency and storage.

## Decision
- The first `SearchBackend` is lexical: Postgres full-text search on card text, trigram name matching, and filters on color identity, types, keywords, tags, mana value and legality.
- `similar_cards` uses shared Tagger tags first ("same role") and text overlap second.
- A vector backend can be added behind the same `SearchBackend` protocol and compared on the same eval set before switching.

## Consequences
- No embedding cost or vector column in the POC.
- "Same vibe" questions depend on tag quality; the eval set must cover them.

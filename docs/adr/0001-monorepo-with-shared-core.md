# 0001: One monorepo, with the shared contract in packages/core

Status: accepted
Date: 2026-11-21

## Context
The API, the ingest job and the evals all need the same card and search types. The web app needs the API's OpenAPI document and stream-event schema. Keeping them in separate repos means version drift between parts that change together.

## Decision
- One repo, `Cardwise-ai/cardwise`: a uv workspace for Python (`packages/*`, `api`, `ingest`, `evals`) and a pnpm workspace for the web (`apps/*`).
- `packages/core` (`cardwise_core`) holds the shared contract: card enums, the search tool inputs (`CardQuery`, `CardLookup`, `RulingsLookup`, `SimilarQuery`), `CardHit`, and the `SearchBackend` protocol. It depends only on Pydantic.
- `packages/llm` (`cardwise_llm`) holds the provider-neutral model port (ADR 0003).
- Retrieval backends implement `SearchBackend`; the API builds tool specs from the core models.
- JSON Schemas and the OpenAPI document are generated and committed; CI fails if they drift.

## Consequences
- A contract change and every consumer update ship in one commit.
- Two package managers in one repo; CI runs a job per side.
- Changes to the spec's layout: `packages/core` was added, and migrations live in `supabase/migrations` (Supabase CLI convention) instead of `db/migrations`.

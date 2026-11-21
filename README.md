# Cardwise

Ask questions about Magic: The Gathering cards and get answers that link to the cards. Cardwise is a chat assistant over Scryfall card data and Scryfall Tagger tags. Deckbuilding stays on Moxfield and Archidekt.

Design and research live in [Cardwise-ai/research](https://github.com/Cardwise-ai/research). Decisions are recorded in [docs/adr](docs/adr). Hosted services (Supabase, Vercel, model providers) are set up with [docs/external-services.md](docs/external-services.md).

## Layout

| Path | What it is |
|---|---|
| `packages/core` | Shared card and search contract (Pydantic) |
| `packages/llm` | Provider-neutral model port, adapters and a fake model for tests |
| `api` | FastAPI app: chats, card search, streamed answers |
| `ingest` | Loads Scryfall bulk data into the corpus |
| `evals` | Answer quality checks |
| `apps/web` | Next.js web app |
| `supabase` | Database migrations, config and schema tests |

## Setup

Needs Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 22 with pnpm, and Docker for the local database.

```sh
uv sync --all-packages
pnpm install
uv run pre-commit install
```

## Checks

```sh
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest -m "not db and not live"

pnpm format:check
pnpm lint
pnpm typecheck
pnpm build
```

Database tests need the local Supabase database:

```sh
pnpm exec supabase db start
uv run pytest -m db
```

After changing a contract model, regenerate the committed schemas:

```sh
uv run python -m cardwise_core.schemas
uv run python -m cardwise_api.export_schemas
```

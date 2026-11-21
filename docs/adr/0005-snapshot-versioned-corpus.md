# 0005: Snapshot-versioned corpus, raw files in Supabase Storage

Status: accepted
Date: 2026-11-21

## Context
Card data comes from Scryfall bulk files (oracle cards, oracle tags, rulings), about 37 MB compressed per snapshot. Reads must never see a half-loaded snapshot, and a bad load must be easy to roll back. The spec first proposed a schema per snapshot swapped by rename, and Cloudflare R2 for raw files.

## Decision
- Every corpus table has a `snapshot_id` column referencing `corpus.snapshots`. A snapshot moves through `loading`, `validated`, `active`, `retired` or `failed`. A partial unique index allows only one `active` snapshot. Activation is one transaction; rollback is reactivating the previous snapshot.
- Deleting a snapshot cascades to its rows. Between runs we keep the active snapshot and the previous one. Before a load, every snapshot but the active one is deleted and vacuumed, so at most two snapshots ever exist.
- Raw bulk files go to a private Supabase Storage bucket, `raw-snapshots`, keeping the last 4 (Free plan: 1 GB storage, 50 MB per file). Cloudflare R2 is dropped.
- Records that fail validation go to `corpus.quarantine` instead of being loaded.
- `corpus.card_tags` holds direct Tagger taggings only. Materializing inherited tags would add ~200k rows per snapshot (measured 2026-11-21), so queries resolve the hierarchy through `corpus.tag_parents`.
- `corpus.snapshots.content_sha256` (hash of the bulk files' hashes) makes a rerun on unchanged files a no-op.
- All `corpus` and `app` tables have RLS enabled with no policies, and the `anon` and `authenticated` roles have no grants. Only the API reaches them.
- `app.message_cards` stores the card name at answer time and has no foreign key to the corpus, so old chats survive snapshot retirement.

## Consequences
- One fixed schema; migrations stay simple.
- Every corpus query must filter by the active snapshot ID.
- Two full snapshots must fit in the 500 MB database limit. Measured on dev after the first loads (2026-11-21): ~180 MB per snapshot, 370 MB for two, before the payload was cut to card facts (14 MB of JSON instead of 34 MB). Embeddings (B7) would add ~120 MB per snapshot at 768 dimensions, so they need their own storage plan.

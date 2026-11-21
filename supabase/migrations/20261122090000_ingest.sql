-- Ingest follow-ups, from profiling the 2026-11-21 Scryfall bulk files.

-- Gleemax has a mana value of 1,000,000; numeric(6, 1) tops out at 99,999.9.
alter table corpus.cards alter column mana_value type numeric(9, 1);

-- Provenance for each snapshot. content_sha256 is the SHA-256 of the per-file hashes and
-- makes re-running ingest on unchanged files a no-op. storage_path is null when the raw
-- files were not archived (local runs).
alter table corpus.snapshots
    alter column storage_path drop not null,
    add column content_sha256 text not null check (content_sha256 ~ '^[0-9a-f]{64}$'),
    add column source_files jsonb not null check (jsonb_typeof(source_files) = 'object');

create index snapshots_content on corpus.snapshots (content_sha256);

-- Face stats are needed for card detail; the cards row keeps only the joined text.
alter table corpus.card_faces
    add column power text,
    add column toughness text,
    add column loyalty text,
    add column defense text;

-- Only direct taggings are stored. Materializing inherited tags added ~200k rows per
-- snapshot; queries resolve the hierarchy through tag_parents instead.
alter table corpus.card_tags drop column inherited;

create index tag_parents_parent on corpus.tag_parents (snapshot_id, parent_id);

comment on table corpus.card_tags is
    'Direct Tagger taggings. A card has tag T if it has T or any descendant of T in tag_parents.';

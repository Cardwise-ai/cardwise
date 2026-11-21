-- Cardwise initial schema.
-- corpus: Scryfall data, versioned by snapshot. Only the API (postgres role) reads it.
-- app: user chats. Only the API writes it; the browser never talks to these tables.
-- Every table has RLS enabled and no policies, and API roles get no grants, so the
-- Data API cannot reach any of it even if a schema is exposed by mistake.

create extension if not exists pg_trgm with schema extensions;

create schema corpus;
create schema app;

revoke all on schema corpus, app from public, anon, authenticated;

-- corpus -------------------------------------------------------------------

create table corpus.snapshots (
    id bigint generated always as identity primary key,
    status text not null default 'loading'
        check (status in ('loading', 'validated', 'active', 'retired', 'failed')),
    source_updated_at timestamptz not null,
    storage_path text not null,
    card_count integer check (card_count >= 0),
    tag_count integer check (tag_count >= 0),
    ruling_count integer check (ruling_count >= 0),
    notes text,
    created_at timestamptz not null default now(),
    activated_at timestamptz,
    check ((status = 'active') = (activated_at is not null) or status = 'retired')
);

-- At most one snapshot serves reads at any time.
create unique index snapshots_one_active on corpus.snapshots ((true)) where status = 'active';

create table corpus.cards (
    snapshot_id bigint not null references corpus.snapshots (id) on delete cascade,
    oracle_id uuid not null,
    name text not null check (char_length(name) between 1 and 300),
    layout text not null,
    is_game_card boolean not null,
    mana_cost text,
    mana_value numeric(6, 1) not null check (mana_value >= 0),
    type_line text not null,
    oracle_text text,
    colors text[] not null default '{}',
    color_identity text[] not null default '{}',
    keywords text[] not null default '{}',
    legalities jsonb not null,
    image_uris jsonb,
    scryfall_uri text not null,
    edhrec_rank integer,
    released_at date,
    search_text text not null,
    search_tsv tsvector generated always as (to_tsvector('english', search_text)) stored,
    payload jsonb not null,
    primary key (snapshot_id, oracle_id),
    check (colors <@ array['W', 'U', 'B', 'R', 'G']),
    check (color_identity <@ array['W', 'U', 'B', 'R', 'G'])
);

create index cards_name_lower on corpus.cards (snapshot_id, lower(name));
create index cards_name_trgm on corpus.cards using gin (name extensions.gin_trgm_ops);
create index cards_search_tsv on corpus.cards using gin (search_tsv);
create index cards_color_identity on corpus.cards using gin (color_identity);
create index cards_keywords on corpus.cards using gin (keywords);

create table corpus.card_faces (
    snapshot_id bigint not null,
    oracle_id uuid not null,
    face_index smallint not null check (face_index >= 0),
    name text not null,
    mana_cost text,
    type_line text,
    oracle_text text,
    image_uris jsonb,
    primary key (snapshot_id, oracle_id, face_index),
    foreign key (snapshot_id, oracle_id)
        references corpus.cards (snapshot_id, oracle_id) on delete cascade
);

create table corpus.rulings (
    id bigint generated always as identity primary key,
    snapshot_id bigint not null,
    oracle_id uuid not null,
    source text not null check (source in ('wotc', 'scryfall')),
    published_at date not null,
    comment text not null,
    foreign key (snapshot_id, oracle_id)
        references corpus.cards (snapshot_id, oracle_id) on delete cascade
);

create index rulings_card on corpus.rulings (snapshot_id, oracle_id);

create table corpus.tags (
    snapshot_id bigint not null references corpus.snapshots (id) on delete cascade,
    tag_id uuid not null,
    slug text not null check (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
    label text not null,
    description text,
    aliases text[] not null default '{}',
    primary key (snapshot_id, tag_id),
    unique (snapshot_id, slug)
);

create table corpus.tag_parents (
    snapshot_id bigint not null,
    tag_id uuid not null,
    parent_id uuid not null,
    primary key (snapshot_id, tag_id, parent_id),
    check (tag_id <> parent_id),
    foreign key (snapshot_id, tag_id)
        references corpus.tags (snapshot_id, tag_id) on delete cascade,
    foreign key (snapshot_id, parent_id)
        references corpus.tags (snapshot_id, tag_id) on delete cascade
);

-- inherited = the card has a child of this tag rather than the tag itself.
create table corpus.card_tags (
    snapshot_id bigint not null,
    tag_id uuid not null,
    oracle_id uuid not null,
    weight text not null check (weight in ('median', 'strong', 'very_strong')),
    annotation text,
    inherited boolean not null default false,
    primary key (snapshot_id, tag_id, oracle_id),
    foreign key (snapshot_id, tag_id)
        references corpus.tags (snapshot_id, tag_id) on delete cascade,
    foreign key (snapshot_id, oracle_id)
        references corpus.cards (snapshot_id, oracle_id) on delete cascade
);

create index card_tags_card on corpus.card_tags (snapshot_id, oracle_id);

-- Records that failed validation during ingest, kept for review instead of loaded.
create table corpus.quarantine (
    id bigint generated always as identity primary key,
    snapshot_id bigint not null references corpus.snapshots (id) on delete cascade,
    source text not null check (source in ('cards', 'tags', 'rulings')),
    record_key text,
    reason text not null,
    payload jsonb not null,
    created_at timestamptz not null default now()
);

-- app ----------------------------------------------------------------------

create table app.chats (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users (id) on delete cascade,
    title text not null check (char_length(title) between 1 and 120),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index chats_user_recent on app.chats (user_id, updated_at desc);

create table app.messages (
    id uuid primary key default gen_random_uuid(),
    chat_id uuid not null references app.chats (id) on delete cascade,
    role text not null check (role in ('user', 'assistant')),
    content text not null check (char_length(content) <= 20000),
    status text not null default 'complete'
        check (status in ('complete', 'interrupted', 'failed')),
    model text,
    usage jsonb,
    created_at timestamptz not null default now(),
    check (role = 'assistant' or (status = 'complete' and model is null and usage is null))
);

create index messages_chat_order on app.messages (chat_id, created_at);

-- Card links shown under a message. No FK to corpus: snapshots are retired, but old
-- chats must keep their links, so the name at answer time is stored here.
create table app.message_cards (
    message_id uuid not null references app.messages (id) on delete cascade,
    position smallint not null check (position between 0 and 99),
    oracle_id uuid not null,
    name text not null check (char_length(name) between 1 and 300),
    primary key (message_id, oracle_id),
    unique (message_id, position)
);

-- Fixed-window counters for per-user rate limits and provider daily quotas.
create table app.usage_counters (
    subject text not null,
    kind text not null,
    window_start timestamptz not null,
    count integer not null default 0 check (count >= 0),
    primary key (subject, kind, window_start)
);

-- lock down ---------------------------------------------------------------

do $$
declare
    t record;
begin
    for t in
        select schemaname, tablename from pg_tables where schemaname in ('corpus', 'app')
    loop
        execute format('alter table %I.%I enable row level security', t.schemaname, t.tablename);
        execute format(
            'revoke all on table %I.%I from public, anon, authenticated',
            t.schemaname,
            t.tablename
        );
    end loop;
end
$$;

revoke all on all sequences in schema corpus, app from public, anon, authenticated;
revoke all on all functions in schema corpus, app from public, anon, authenticated;

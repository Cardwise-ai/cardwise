-- Retrieval: card lookup matches face names ("Stomp" finds Bonecrusher Giant // Stomp)
-- case-insensitively within the active snapshot. Mirrors cards_name_lower.
create index card_faces_name_lower on corpus.card_faces (snapshot_id, lower(name));

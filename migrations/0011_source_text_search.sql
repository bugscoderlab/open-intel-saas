-- 0011: Full-text search index on research.sources (ticket #25, spec #21).
--
-- Keyword search runs to_tsvector over title + full_text (ticket #25's
-- query mirrors this expression exactly). The GIN index keeps the
-- tsvector match cheap as projects accumulate sources; without it every
-- search seq-scans. Vector search needs no index yet — the managed
-- project's chunk counts are tiny and sequential scan + top-k sort is
-- fine at this scale (an IVFFlat/HNSW index is a later optimization).

create index if not exists sources_text_search_idx on research.sources
    using gin (to_tsvector('english', title || ' ' || coalesce(full_text, '')));

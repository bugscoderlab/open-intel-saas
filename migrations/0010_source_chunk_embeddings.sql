-- 0010: Embeddings on research.source_chunks (ticket #24, spec #21).
--
-- Chunks become embeddable: one vector(1536) per chunk row (plan §9),
-- written by the async pipeline after token-based chunking. Expand phase
-- of the source_chunks contract — no backfill needed: chunks written
-- before this migration were test rows only, and the pipeline's
-- delete-and-reinsert makes every (re)processing write complete rows.

create extension if not exists vector with schema extensions;

alter table research.source_chunks
    add column if not exists embedding extensions.vector(1536);

-- 0013: Research module — file Sources (ticket #29, spec #26,
-- Phase 2 backfill 2/3).
--
-- Widen the sources.type CHECK to admit 'file' (ticket #23 created it as
-- ('text')). Drop + recreate, no data rewrite: every existing row is
-- 'text' and stays valid. The pipeline distinguishes paths by type;
-- file sources carry no text at rest until the async extraction lands
-- it in full_text.

alter table research.sources drop constraint if exists sources_type_check;
alter table research.sources add constraint sources_type_check
    check (type in ('text', 'file'));

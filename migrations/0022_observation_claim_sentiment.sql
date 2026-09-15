-- 0022: Observations — claim text + sentiment (ticket #56, spec #47/#52)
--
-- Phase 5's extraction carries a normalized claim and (for review
-- topics) a sentiment on every extracted item, but observations had no
-- columns to hold them — review topics aggregate by topic identity and
-- sentiment, so the durable fact needs both. Additive, nullable;
-- manual price observations leave them NULL.

alter table competitor.observations
    add column if not exists claim text,
    add column if not exists sentiment text
        check (sentiment in ('positive', 'neutral', 'negative'));

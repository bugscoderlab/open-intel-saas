-- 0009: Research source grants (ticket #23, spec #21).
--
-- Same dedicated-schema gap as 0007: the public schema grants the API
-- roles USAGE/ALL via Supabase default privileges; research.* gets
-- neither. Row access is still governed entirely by the RLS policies —
-- SELECT is all the API roles need. (Schema USAGE was granted in 0007.)

grant select on research.sources to anon, authenticated;
grant select on research.source_chunks to anon, authenticated;

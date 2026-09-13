-- 0007: Research schema grants (ticket #22, spec #21).
--
-- The public schema grants USAGE on the schema and ALL on its tables to
-- the API roles (anon, authenticated) via Supabase default privileges;
-- a dedicated schema (plan §14.4) gets neither. Without these the RLS
-- safety net on research.notebooks errors instead of denying.
-- Row access is still governed entirely by the RLS policies — SELECT is
-- all the API roles need.

grant usage on schema research to anon, authenticated;
grant select on research.notebooks to anon, authenticated;

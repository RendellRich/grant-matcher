-- pg_net can't change schema in place, so it is reinstalled in "extensions". Its functions stay in schema "net",
-- so the weekly-email schedule (net.http_post) is unchanged.
drop extension if exists pg_net;
create extension pg_net with schema extensions;

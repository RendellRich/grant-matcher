-- The email job reads every reply as JSON, and a void function replies with nothing. Return whether it saved.
drop function public.finish_digest(uuid, text[]);
create function public.finish_digest(p_id uuid, p_seen text[])
returns boolean language sql security definer set search_path = '' as $$
  with done as (update public.accounts set digest_seen = p_seen where id = p_id and digest_on returning 1)
  select exists (select 1 from done);
$$;
revoke execute on function public.finish_digest(uuid, text[]) from public, anon, authenticated;
grant execute on function public.finish_digest(uuid, text[]) to service_role;

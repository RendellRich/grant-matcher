-- Free accounts no longer have a monthly search limit: they see the top ten matches in each source, and only
-- an active Pro or Consultant plan gets the full lists (supabase/functions/search). record_search() now says
-- which of the two a signed-in account gets, and still logs each search once a month, as a hash.

drop function public.record_search(text);

create function public.record_search(p_sig text default null)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  acct public.accounts%rowtype;
  paid boolean;
  month_start timestamptz := date_trunc('month', now());
  seen boolean := false;
begin
  select * into acct from public.accounts where owner = (select auth.uid());
  if not found then
    return jsonb_build_object('full', false, 'reason', 'signed_out');
  end if;
  if p_sig is not null and length(p_sig) > 128 then
    raise exception 'search signature too long';
  end if;
  paid := acct.plan in ('pro', 'consultant') and acct.status in ('active', 'trialing');
  if p_sig is not null then
    select exists (
      select 1 from public.search_log
      where account_id = acct.id and sig = p_sig and ran_at >= month_start
    ) into seen;
  end if;
  if not seen then
    insert into public.search_log (account_id, sig) values (acct.id, p_sig);
  end if;
  return jsonb_build_object('full', paid, 'plan', acct.plan, 'repeat', seen);
end;
$$;
revoke execute on function public.record_search(text) from public, anon;
grant execute on function public.record_search(text) to authenticated;

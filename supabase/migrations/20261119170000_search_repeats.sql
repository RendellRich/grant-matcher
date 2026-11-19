-- A search is counted once a month. Running the same search again (the same mission, key words, place and
-- focus, which the search function sends as a hash) is free, and so are refinements such as deadlines,
-- award sizes and the hide list, which never change the hash. Adds the private data bucket the search
-- function reads; only the service role can read or write it.

alter table public.search_log add column sig text;
create index search_log_account_sig_idx on public.search_log (account_id, sig, ran_at desc);

drop function public.record_search();

create function public.record_search(p_sig text default null)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  acct public.accounts%rowtype;
  used int;
  lim int;
  month_start timestamptz := date_trunc('month', now());
begin
  select * into acct from public.accounts where owner = (select auth.uid());
  if not found then
    return jsonb_build_object('allowed', false, 'reason', 'signed_out');
  end if;
  if p_sig is not null and length(p_sig) > 128 then
    raise exception 'search signature too long';
  end if;
  lim := case when acct.plan in ('pro', 'consultant') and acct.status in ('active', 'trialing') then null else 3 end;
  select count(*) into used from public.search_log
    where account_id = acct.id and ran_at >= month_start;
  if p_sig is not null and exists (
    select 1 from public.search_log
    where account_id = acct.id and sig = p_sig and ran_at >= month_start
  ) then
    return jsonb_build_object('allowed', true, 'repeat', true, 'used', used, 'limit', lim, 'plan', acct.plan);
  end if;
  if lim is not null and used >= lim then
    return jsonb_build_object('allowed', false, 'reason', 'limit', 'used', used, 'limit', lim, 'plan', acct.plan);
  end if;
  insert into public.search_log (account_id, sig) values (acct.id, p_sig);
  return jsonb_build_object('allowed', true, 'used', used + 1, 'limit', lim, 'plan', acct.plan);
end;
$$;
revoke execute on function public.record_search(text) from public, anon;
grant execute on function public.record_search(text) to authenticated;

-- Where the exported data lives now that the public site no longer serves it. Private: no storage policies,
-- so only the service role (the search function and the data upload) can reach it.
insert into storage.buckets (id, name, public)
values ('data', 'data', false)
on conflict (id) do nothing;

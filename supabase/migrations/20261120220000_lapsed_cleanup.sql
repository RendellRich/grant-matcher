-- What a paid account saved is kept for a year after the paid plan ends, in case the person comes back, then
-- deleted: the saved profiles and shortlists (Consultant clients included), the weekly email's profile and
-- deadline reminders. The account itself stays, on the Free plan, so the person can still sign in.
-- A plan given by hand never lapses on its own; switching it to free starts the same year.

alter table public.accounts add column plan_ended_at timestamptz;

-- The Stripe webhook switches a lapsed account to free; this dates that, and a new paid plan clears it.
create or replace function private.date_plan_end()
returns trigger language plpgsql set search_path = '' as $$
begin
  if new.plan = 'free' and old.plan in ('pro', 'consultant') then new.plan_ended_at := now();
  elsif new.plan in ('pro', 'consultant') then new.plan_ended_at := null;
  end if;
  return new;
end;
$$;
revoke execute on function private.date_plan_end() from public, anon, authenticated;
create trigger accounts_date_plan_end before update of plan on public.accounts
  for each row execute function private.date_plan_end();

-- Deletes what lapsed accounts saved, a year after the plan ended. Returns how many accounts it cleared.
create or replace function private.clean_lapsed()
returns int language plpgsql security definer set search_path = '' as $$
declare
  ids uuid[];
begin
  select coalesce(array_agg(a.id), '{}') into ids from public.accounts a
  where a.plan = 'free' and a.plan_ended_at < now() - interval '1 year'
    and (exists (select 1 from public.profiles p where p.account_id = a.id)
      or exists (select 1 from public.reminders r where r.account_id = a.id)
      or a.digest_profile is not null or a.digest_on or a.remind_on);
  if cardinality(ids) = 0 then return 0; end if;
  delete from public.profiles where account_id = any (ids);      -- their shortlists go with them
  delete from public.reminders where account_id = any (ids);
  update public.accounts set digest_on = false, digest_profile = null, digest_vector = null, digest_seen = null,
    remind_on = false where id = any (ids);
  return cardinality(ids);
end;
$$;
revoke execute on function private.clean_lapsed() from public, anon, authenticated;

-- Every day at 4:17 am UTC.
select cron.schedule('clean-lapsed-accounts', '17 4 * * *', $$ select private.clean_lapsed(); $$);

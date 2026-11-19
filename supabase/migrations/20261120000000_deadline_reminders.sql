-- Deadline reminders (Pro and Consultant): an email 14 days and 3 days before each shortlisted deadline.
-- The shortlist lives in the browser, so while reminders are on the page sends the open shortlisted grants
-- with their deadlines (set_reminders), and replaces the set whenever the shortlist changes.
-- supabase/functions/deadline-reminders sends what is due each morning and marks it sent.
alter table public.accounts add column remind_on boolean not null default false;

create table public.reminders (
  account_id uuid not null references public.accounts (id) on delete cascade,
  key text not null,
  title text not null,
  url text not null default '',
  source text not null default '',
  stage text not null default 'saved',
  due date not null,
  sent14 boolean not null default false,
  sent3 boolean not null default false,
  primary key (account_id, key)
);
alter table public.reminders enable row level security;
revoke all on public.reminders from anon, authenticated;
create index reminders_pending_idx on public.reminders (due) where not (sent14 and sent3);

-- The page's view of the account's emails: the weekly email and the reminders.
create or replace function public.my_digest()
returns jsonb language sql stable security definer set search_path = '' as $$
  select coalesce((select jsonb_build_object('on', a.digest_on, 'sent_at', a.digest_sent_at, 'profile', a.digest_profile,
      'reminders', a.remind_on, 'reminder_count', (select count(*) from public.reminders r where r.account_id = a.id))
    from public.accounts a where a.owner = (select auth.uid())), jsonb_build_object('on', false, 'reminders', false));
$$;

-- Turns reminders on with this set of shortlisted grants (replacing the last set), or off (deleting them).
-- A grant whose date changed gets both reminders again.
create or replace function public.set_reminders(p_on boolean, p_items jsonb)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  acct public.accounts%rowtype;
begin
  select * into acct from public.accounts where owner = (select auth.uid());
  if not found then raise exception 'no account'; end if;
  if not p_on then
    update public.accounts set remind_on = false where id = acct.id;
    delete from public.reminders where account_id = acct.id;
    return public.my_digest();
  end if;
  if not (acct.plan in ('pro', 'consultant') and acct.status in ('active', 'trialing', 'past_due')) then
    raise exception 'Deadline reminders come with Pro.';
  end if;
  if p_items is null or jsonb_typeof(p_items) <> 'array' or jsonb_array_length(p_items) > 300 then
    raise exception 'Send a list';
  end if;
  update public.accounts set remind_on = true where id = acct.id;
  with incoming as (
    select distinct on (e->>'key') left(e->>'key', 200) as key, left(coalesce(e->>'title', ''), 300) as title,
      left(coalesce(e->>'url', ''), 500) as url, left(coalesce(e->>'source', ''), 10) as source,
      case when e->>'stage' = 'applying' then 'applying' else 'saved' end as stage, (e->>'due')::date as due
    from jsonb_array_elements(p_items) e
    where e->>'key' is not null and coalesce(e->>'due', '') ~ '^\d{4}-\d{2}-\d{2}$'
  ), gone as (
    delete from public.reminders r where r.account_id = acct.id and r.key not in (select key from incoming)
  )
  insert into public.reminders (account_id, key, title, url, source, stage, due)
  select acct.id, key, title, url, source, stage, due from incoming
  on conflict (account_id, key) do update set title = excluded.title, url = excluded.url, source = excluded.source,
    stage = excluded.stage, due = excluded.due,
    sent14 = case when public.reminders.due = excluded.due then public.reminders.sent14 else false end,
    sent3 = case when public.reminders.due = excluded.due then public.reminders.sent3 else false end;
  return public.my_digest();
end;
$$;
revoke execute on function public.set_reminders(boolean, jsonb) from public, anon;
grant execute on function public.set_reminders(boolean, jsonb) to authenticated;

-- ---------- for the reminder job only (service role) ----------
-- Accounts with a reminder to send today (Eastern time): the two-week one from 14 days out until 4 days out,
-- the three-day one from 3 days out until the day itself, each once.
create or replace function public.due_reminders(p_limit int default 25)
returns jsonb language sql stable security definer set search_path = '' as $$
  with today as (select (now() at time zone 'America/New_York')::date as d),
  due as (
    select r.*, r.due - (select d from today) as days from public.reminders r
    join public.accounts a on a.id = r.account_id
    where a.remind_on and a.plan in ('pro', 'consultant') and a.status in ('active', 'trialing', 'past_due')
      and ((not r.sent14 and r.due - (select d from today) between 4 and 14)
        or (not r.sent3 and r.due - (select d from today) between 0 and 3))
  ), accts as (
    select account_id from due group by account_id order by min(days) limit greatest(1, least(p_limit, 100))
  )
  select coalesce(jsonb_agg(jsonb_build_object('account_id', a.id, 'email', u.email, 'token', a.digest_token,
    'items', (select jsonb_agg(jsonb_build_object('key', d.key, 'title', d.title, 'url', d.url, 'source', d.source,
      'stage', d.stage, 'due', d.due, 'days', d.days) order by d.days) from due d where d.account_id = a.id))), '[]'::jsonb)
  from accts x join public.accounts a on a.id = x.account_id join auth.users u on u.id = a.owner;
$$;

-- After an email went out: these reminders are sent. A grant 3 days out or less has had its last one.
create or replace function public.mark_reminders(p_account uuid, p_keys text[])
returns boolean language sql security definer set search_path = '' as $$
  with done as (
    update public.reminders set sent14 = true,
      sent3 = sent3 or due - (now() at time zone 'America/New_York')::date <= 3
    where account_id = p_account and key = any (p_keys) returning 1
  ) select exists (select 1 from done);
$$;

-- The reminder email's turn-off link (the account's email token, the same one the weekly email uses).
create or replace function public.reminders_off(p_token uuid)
returns boolean language plpgsql security definer set search_path = '' as $$
declare
  acct uuid;
begin
  update public.accounts set remind_on = false where digest_token = p_token and remind_on returning id into acct;
  if acct is null then return false; end if;
  delete from public.reminders where account_id = acct;
  return true;
end;
$$;

insert into private.job_tokens (name) values ('deadline-reminders');

revoke execute on function public.due_reminders(int) from public, anon, authenticated;
revoke execute on function public.mark_reminders(uuid, text[]) from public, anon, authenticated;
revoke execute on function public.reminders_off(uuid) from public, anon, authenticated;
grant execute on function public.due_reminders(int) to service_role;
grant execute on function public.mark_reminders(uuid, text[]) to service_role;
grant execute on function public.reminders_off(uuid) to service_role;

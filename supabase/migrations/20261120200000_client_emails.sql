-- Consultant emails. The weekly email can cover each client: one email per client, or one combined email with
-- a section per client (accounts.digest_mode). Each client is turned on separately and remembers what it was
-- already sent (profiles.digest_on, digest_seen); the email uses the client's saved profile. Deadline reminders
-- cover every client's shortlist: each reminder row belongs to a client (reminders.client, '' on Pro), and the
-- page replaces one client's rows at a time. Pro keeps the single weekly email from 20261119220000.

alter table public.accounts add column digest_mode text not null default 'each' check (digest_mode in ('each', 'combined'));
alter table public.profiles
  add column digest_on boolean not null default false,
  add column digest_seen text[];

alter table public.reminders
  add column client text not null default '',
  add column client_label text not null default '';
alter table public.reminders drop constraint reminders_pkey;
alter table public.reminders add primary key (account_id, client, key);

-- A Consultant account that already had the weekly email keeps it, for its first client.
update public.profiles p set digest_on = true, digest_seen = a.digest_seen,
  profile = case when p.profile = '{}'::jsonb then a.digest_profile else p.profile end,
  vector = case when p.profile = '{}'::jsonb then a.digest_vector else p.vector end
from public.accounts a
where a.id = p.account_id and a.plan = 'consultant' and a.digest_on and a.digest_profile is not null
  and p.id = (select x.id from public.profiles x where x.account_id = a.id order by x.created_at, x.id limit 1);

-- The page's view of the account's emails. Consultant also gets its clients and whether each is on.
create or replace function public.my_digest()
returns jsonb language sql stable security definer set search_path = '' as $$
  select coalesce((select jsonb_build_object('on', a.digest_on, 'sent_at', a.digest_sent_at, 'profile', a.digest_profile,
      'reminders', a.remind_on, 'reminder_count', (select count(*) from public.reminders r where r.account_id = a.id),
      'plan', a.plan, 'mode', a.digest_mode,
      'clients', (select coalesce(jsonb_agg(jsonb_build_object('id', p.id, 'label', p.label, 'on', p.digest_on,
          'ready', p.profile <> '{}'::jsonb) order by p.created_at, p.id), '[]'::jsonb)
        from public.profiles p where p.account_id = a.id))
    from public.accounts a where a.owner = (select auth.uid())), jsonb_build_object('on', false, 'reminders', false));
$$;

-- Consultant: turns the weekly email on or off for one client. The account's email is on while any client is.
create or replace function public.save_client_digest(p_id uuid, p_on boolean)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  acct public.accounts%rowtype;
  prof public.profiles%rowtype;
begin
  acct := private.my_account();
  if not (private.paid(acct.plan, acct.status) and acct.plan = 'consultant') then raise exception 'Client emails come with Consultant.'; end if;
  select * into prof from public.profiles where id = p_id and account_id = acct.id;
  if not found then raise exception 'That client isn''t on this account.'; end if;
  if p_on and prof.profile = '{}'::jsonb then raise exception 'Search with this client''s profile first.'; end if;
  update public.profiles set digest_on = p_on, digest_seen = case when p_on and not digest_on then null else digest_seen end
    where id = p_id;
  update public.accounts set
    digest_sent_at = case when digest_on then digest_sent_at else null end,
    digest_on = exists (select 1 from public.profiles x where x.account_id = acct.id and x.digest_on)
    where id = acct.id;
  return public.my_digest();
end;
$$;

create or replace function public.set_digest_mode(p_mode text)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  acct public.accounts%rowtype;
begin
  acct := private.my_account();
  if p_mode not in ('each', 'combined') then raise exception 'Pick each or combined.'; end if;
  update public.accounts set digest_mode = p_mode where id = acct.id;
  return public.my_digest();
end;
$$;

-- For the email job: the account most overdue, with its clients when it is a Consultant account.
create or replace function public.take_digest()
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  row jsonb;
begin
  with due as (
    select a.id from public.accounts a
    where a.digest_on and a.plan in ('pro', 'consultant') and a.status in ('active', 'trialing', 'past_due')
      and (a.digest_sent_at is null or a.digest_sent_at < now() - interval '7 days')
    order by a.digest_sent_at nulls first limit 1 for update skip locked
  ), took as (
    update public.accounts a set digest_sent_at = now() from due where a.id = due.id
    returning a.id, a.owner, a.plan, a.digest_mode, a.digest_profile, a.digest_vector, a.digest_seen, a.digest_token
  )
  select jsonb_build_object('id', t.id, 'email', u.email, 'profile', t.digest_profile, 'vector', t.digest_vector,
    'seen', t.digest_seen, 'token', t.digest_token, 'mode', t.digest_mode,
    'clients', case when t.plan = 'consultant' then (
      select coalesce(jsonb_agg(jsonb_build_object('id', p.id, 'label', p.label, 'profile', p.profile, 'vector', p.vector,
        'seen', p.digest_seen) order by p.created_at, p.id), '[]'::jsonb)
      from public.profiles p where p.account_id = t.id and p.digest_on and p.profile <> '{}'::jsonb) end)
  into row from took t join auth.users u on u.id = t.owner;
  return row;
end;
$$;

-- After a Consultant run: what each client has now been sent (p_seen maps client id to its strong-match keys).
create or replace function public.finish_client_digests(p_id uuid, p_seen jsonb)
returns void language sql security definer set search_path = '' as $$
  update public.profiles p set digest_seen = array(select jsonb_array_elements_text(p_seen -> p.id::text))
  where p.account_id = p_id and p.digest_on and p_seen ? p.id::text;
$$;

create or replace function public.digest_off(p_token uuid)
returns boolean language plpgsql security definer set search_path = '' as $$
declare
  acct uuid;
begin
  update public.accounts set digest_on = false, digest_profile = null, digest_vector = null, digest_seen = null
    where digest_token = p_token and digest_on returning id into acct;
  if acct is null then return false; end if;
  update public.profiles set digest_on = false, digest_seen = null where account_id = acct;
  return true;
end;
$$;

-- Reminders for one client's shortlist (p_id; null on Pro), replacing that client's last set. Off deletes all.
drop function public.set_reminders(boolean, jsonb);
create or replace function public.set_reminders(p_on boolean, p_items jsonb, p_id uuid default null)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  acct public.accounts%rowtype;
  who text := coalesce(p_id::text, '');
  label text := '';
begin
  acct := private.my_account();
  if not p_on then
    update public.accounts set remind_on = false where id = acct.id;
    delete from public.reminders where account_id = acct.id;
    return public.my_digest();
  end if;
  if not private.paid(acct.plan, acct.status) then raise exception 'Deadline reminders come with Pro.'; end if;
  if p_items is null or jsonb_typeof(p_items) <> 'array' or jsonb_array_length(p_items) > 300 then
    raise exception 'Send a list';
  end if;
  if p_id is not null then
    select x.label into label from public.profiles x where x.id = p_id and x.account_id = acct.id;
    if not found then raise exception 'That client isn''t on this account.'; end if;
  end if;
  update public.accounts set remind_on = true where id = acct.id;
  with incoming as (
    select distinct on (e->>'key') left(e->>'key', 200) as key, left(coalesce(e->>'title', ''), 300) as title,
      left(coalesce(e->>'url', ''), 500) as url, left(coalesce(e->>'source', ''), 10) as source,
      case when e->>'stage' = 'applying' then 'applying' else 'saved' end as stage, (e->>'due')::date as due
    from jsonb_array_elements(p_items) e
    where e->>'key' is not null and coalesce(e->>'due', '') ~ '^\d{4}-\d{2}-\d{2}$'
  ), gone as (
    delete from public.reminders r where r.account_id = acct.id and r.client = who and r.key not in (select key from incoming)
  )
  insert into public.reminders (account_id, client, client_label, key, title, url, source, stage, due)
  select acct.id, who, coalesce(label, ''), key, title, url, source, stage, due from incoming
  on conflict (account_id, client, key) do update set client_label = excluded.client_label, title = excluded.title,
    url = excluded.url, source = excluded.source, stage = excluded.stage, due = excluded.due,
    sent14 = case when public.reminders.due = excluded.due then public.reminders.sent14 else false end,
    sent3 = case when public.reminders.due = excluded.due then public.reminders.sent3 else false end;
  return public.my_digest();
end;
$$;
revoke execute on function public.set_reminders(boolean, jsonb, uuid) from public, anon;
grant execute on function public.set_reminders(boolean, jsonb, uuid) to authenticated;

-- The reminder job's view now says which client each grant is for.
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
    'items', (select jsonb_agg(jsonb_build_object('key', d.key, 'client', d.client, 'client_label', d.client_label,
      'title', d.title, 'url', d.url, 'source', d.source, 'stage', d.stage, 'due', d.due, 'days', d.days) order by d.days)
      from due d where d.account_id = a.id))), '[]'::jsonb)
  from accts x join public.accounts a on a.id = x.account_id join auth.users u on u.id = a.owner;
$$;

-- Marks reminders sent. Keys are "client|key"; a plain key (from before clients) matches the Pro row.
create or replace function public.mark_reminders(p_account uuid, p_keys text[])
returns boolean language sql security definer set search_path = '' as $$
  with done as (
    update public.reminders set sent14 = true,
      sent3 = sent3 or due - (now() at time zone 'America/New_York')::date <= 3
    where account_id = p_account and (client || '|' || key = any (p_keys) or (client = '' and key = any (p_keys))) returning 1
  ) select exists (select 1 from done);
$$;

revoke execute on function public.save_client_digest(uuid, boolean) from public, anon;
revoke execute on function public.set_digest_mode(text) from public, anon;
revoke execute on function public.finish_client_digests(uuid, jsonb) from public, anon, authenticated;
grant execute on function public.save_client_digest(uuid, boolean) to authenticated;
grant execute on function public.set_digest_mode(text) to authenticated;
grant execute on function public.finish_client_digests(uuid, jsonb) to service_role;

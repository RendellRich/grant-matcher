-- Grant Matcher accounts: one account per signed-in person, its saved profiles and shortlists, and a log of
-- searches so free accounts can be held to a few a month. Plan and billing fields are written only by the
-- server (Stripe webhook, service role); people can read them and rename their account, nothing more.

create schema if not exists private;

-- ---------- accounts ----------
create table public.accounts (
  id uuid primary key default gen_random_uuid(),
  owner uuid not null unique references auth.users (id) on delete cascade,
  name text not null default '' check (length(name) <= 200),
  plan text not null default 'free' check (plan in ('free', 'pro', 'consultant')),
  status text not null default 'none' check (status in ('none', 'trialing', 'active', 'past_due', 'canceled')),
  stripe_customer_id text unique,
  stripe_subscription_id text unique,
  founding boolean not null default false,
  created_at timestamptz not null default now()
);
alter table public.accounts enable row level security;

create policy "Owners read their account" on public.accounts
  for select to authenticated using (owner = (select auth.uid()));
create policy "Owners rename their account" on public.accounts
  for update to authenticated using (owner = (select auth.uid())) with check (owner = (select auth.uid()));

-- Only the name is theirs to change; plan, status and Stripe ids come from the server.
revoke insert, update, delete on public.accounts from anon, authenticated;
grant select on public.accounts to authenticated;
grant update (name) on public.accounts to authenticated;

-- Every new sign-in gets a free account.
create or replace function private.create_account_for_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.accounts (owner) values (new.id) on conflict (owner) do nothing;
  return new;
end;
$$;
revoke execute on function private.create_account_for_user() from public, anon, authenticated;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function private.create_account_for_user();

-- The caller's own account id, looked up once per statement in policies.
create or replace function private.my_account_id()
returns uuid
language sql
stable
security definer
set search_path = ''
as $$
  select id from public.accounts where owner = (select auth.uid());
$$;
revoke execute on function private.my_account_id() from public, anon;
grant usage on schema private to authenticated;
grant execute on function private.my_account_id() to authenticated;

-- ---------- profiles ----------
create table public.profiles (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references public.accounts (id) on delete cascade,
  label text not null default 'My organization' check (length(label) <= 120),
  profile jsonb not null default '{}'::jsonb,  -- the same shape as the downloadable profile file
  digest_email text check (digest_email is null or length(digest_email) <= 320),
  updated_at timestamptz not null default now()
);
create index profiles_account_id_idx on public.profiles (account_id);
alter table public.profiles enable row level security;

create policy "Owners manage their profiles" on public.profiles
  for all to authenticated
  using (account_id = (select private.my_account_id()))
  with check (account_id = (select private.my_account_id()));
grant select, insert, update, delete on public.profiles to authenticated;

-- How many profiles each plan keeps: one for free and Pro, ten for Consultant.
create or replace function private.profile_limit()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  allowed int;
  have int;
begin
  select case a.plan when 'consultant' then 10 else 1 end into allowed
    from public.accounts a where a.id = new.account_id;
  select count(*) into have from public.profiles p where p.account_id = new.account_id;
  if have >= allowed then
    raise exception 'This plan keeps % saved profile(s).', allowed using errcode = 'P0001';
  end if;
  return new;
end;
$$;
revoke execute on function private.profile_limit() from public, anon, authenticated;

create trigger profiles_limit
  before insert on public.profiles
  for each row execute function private.profile_limit();

-- ---------- shortlist ----------
create table public.shortlist_items (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references public.profiles (id) on delete cascade,
  match_key text not null check (length(match_key) <= 200),
  stage text not null default 'saved' check (stage in ('saved', 'applying', 'submitted', 'awarded', 'declined')),
  own_deadline date,
  stage_changed_at timestamptz not null default now(),
  snapshot jsonb not null default '{}'::jsonb,  -- title, funder, deadline and link when it was saved
  unique (profile_id, match_key)
);
alter table public.shortlist_items enable row level security;

create policy "Owners manage their shortlist" on public.shortlist_items
  for all to authenticated
  using (profile_id in (select id from public.profiles where account_id = (select private.my_account_id())))
  with check (profile_id in (select id from public.profiles where account_id = (select private.my_account_id())));
grant select, insert, update, delete on public.shortlist_items to authenticated;

-- ---------- searches ----------
create table public.search_log (
  id bigint generated always as identity primary key,
  account_id uuid not null references public.accounts (id) on delete cascade,
  ran_at timestamptz not null default now()
);
create index search_log_account_ran_idx on public.search_log (account_id, ran_at desc);
alter table public.search_log enable row level security;

create policy "Owners read their searches" on public.search_log
  for select to authenticated using (account_id = (select private.my_account_id()));
revoke insert, update, delete on public.search_log from anon, authenticated;
grant select on public.search_log to authenticated;

-- Counts a search for the caller and says whether it may run. Free accounts get 3 a calendar month;
-- paid plans are not limited. Called by the site before it shows a full result list.
create or replace function public.record_search()
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  acct public.accounts%rowtype;
  used int;
  lim int;
begin
  select * into acct from public.accounts where owner = (select auth.uid());
  if not found then
    return jsonb_build_object('allowed', false, 'reason', 'signed_out');
  end if;
  lim := case when acct.plan in ('pro', 'consultant') and acct.status in ('active', 'trialing') then null else 3 end;
  select count(*) into used from public.search_log
    where account_id = acct.id and ran_at >= date_trunc('month', now());
  if lim is not null and used >= lim then
    return jsonb_build_object('allowed', false, 'reason', 'limit', 'used', used, 'limit', lim);
  end if;
  insert into public.search_log (account_id) values (acct.id);
  return jsonb_build_object('allowed', true, 'used', used + 1, 'limit', lim);
end;
$$;
revoke execute on function public.record_search() from public, anon;
grant execute on function public.record_search() to authenticated;

-- ---------- server-only tables (no policies: only the service role reads or writes them) ----------
create table public.match_runs (
  profile_id uuid not null references public.profiles (id) on delete cascade,
  run_at timestamptz not null default now(),
  strong jsonb not null default '[]'::jsonb,  -- keys and names of strong matches only
  primary key (profile_id, run_at)
);
alter table public.match_runs enable row level security;

create table public.email_log (
  id bigint generated always as identity primary key,
  profile_id uuid references public.profiles (id) on delete set null,
  kind text not null check (kind in ('digest', 'reminder', 'deadline_moved')),
  match_key text,
  sent_at timestamptz not null default now()
);
create index email_log_profile_id_idx on public.email_log (profile_id);
alter table public.email_log enable row level security;

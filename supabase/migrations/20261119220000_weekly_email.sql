-- The weekly email of new strong matches (Pro and Consultant). An account saves one profile, with the mission
-- vector its browser made, and turns the email on or off. supabase/functions/weekly-email runs every ten
-- minutes (pg_cron), takes one account that is due, and emails the strong matches it hasn't sent before.
-- People change these columns only through save_digest(); the email job uses the service-role functions below.
alter table public.accounts
  add column digest_on boolean not null default false,
  add column digest_profile jsonb,
  add column digest_vector real[],
  add column digest_seen text[],          -- strong-match keys already sent (or seeded); null means seed next run
  add column digest_sent_at timestamptz,  -- when the job last took this account
  add column digest_token uuid not null default gen_random_uuid();  -- the unsubscribe link
create unique index accounts_digest_token_idx on public.accounts (digest_token);
create index accounts_digest_due_idx on public.accounts (digest_sent_at nulls first) where digest_on;

-- What the page shows about the account's weekly email.
create or replace function public.my_digest()
returns jsonb language sql stable security definer set search_path = '' as $$
  select coalesce((select jsonb_build_object('on', a.digest_on, 'sent_at', a.digest_sent_at, 'profile', a.digest_profile)
    from public.accounts a where a.owner = (select auth.uid())), jsonb_build_object('on', false));
$$;

-- Turns the weekly email on for this profile (paid plans only), or off. Turning it off deletes the saved profile.
create or replace function public.save_digest(p_profile jsonb, p_vector real[], p_on boolean)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  acct public.accounts%rowtype;
begin
  select * into acct from public.accounts where owner = (select auth.uid());
  if not found then raise exception 'no account'; end if;
  if p_on then
    if not (acct.plan in ('pro', 'consultant') and acct.status in ('active', 'trialing', 'past_due')) then
      raise exception 'The weekly email comes with Pro.';
    end if;
    if p_profile is null or jsonb_typeof(p_profile) <> 'object' or length(p_profile::text) > 20000 then
      raise exception 'Send a profile';
    end if;
    if p_vector is not null and array_length(p_vector, 1) <> 384 then raise exception 'Bad vector'; end if;
    update public.accounts set digest_on = true, digest_profile = p_profile, digest_vector = p_vector,
      digest_seen = null, digest_sent_at = null where id = acct.id;
  else
    update public.accounts set digest_on = false, digest_profile = null, digest_vector = null, digest_seen = null
      where id = acct.id;
  end if;
  return public.my_digest();
end;
$$;
revoke execute on function public.my_digest() from public, anon;
revoke execute on function public.save_digest(jsonb, real[], boolean) from public, anon;
grant execute on function public.my_digest() to authenticated;
grant execute on function public.save_digest(jsonb, real[], boolean) to authenticated;

-- ---------- for the email job only (service role) ----------
-- Takes the account most overdue (a week since it was last taken, or never) and marks it taken now, so a
-- failing account waits a week instead of blocking the rest.
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
    returning a.id, a.owner, a.digest_profile, a.digest_vector, a.digest_seen, a.digest_token
  )
  select jsonb_build_object('id', t.id, 'email', u.email, 'profile', t.digest_profile, 'vector', t.digest_vector,
    'seen', t.digest_seen, 'token', t.digest_token)
  into row from took t join auth.users u on u.id = t.owner;
  return row;
end;
$$;

create or replace function public.finish_digest(p_id uuid, p_seen text[])
returns void language sql security definer set search_path = '' as $$
  update public.accounts set digest_seen = p_seen where id = p_id and digest_on;
$$;

create or replace function public.digest_off(p_token uuid)
returns boolean language sql security definer set search_path = '' as $$
  with off as (update public.accounts set digest_on = false, digest_profile = null, digest_vector = null, digest_seen = null
    where digest_token = p_token returning 1) select exists (select 1 from off);
$$;

-- The job's own token: made here, read only by pg_cron and the function, never typed by anyone.
create schema if not exists private;
revoke all on schema private from public, anon, authenticated;
create table private.job_tokens (name text primary key, token uuid not null default gen_random_uuid());
insert into private.job_tokens (name) values ('weekly-email');

create or replace function public.check_job_token(p_name text, p_token text)
returns boolean language sql stable security definer set search_path = '' as $$
  select exists (select 1 from private.job_tokens where name = p_name and token::text = p_token);
$$;

revoke execute on function public.take_digest() from public, anon, authenticated;
revoke execute on function public.finish_digest(uuid, text[]) from public, anon, authenticated;
revoke execute on function public.digest_off(uuid) from public, anon, authenticated;
revoke execute on function public.check_job_token(text, text) from public, anon, authenticated;
grant execute on function public.take_digest() to service_role;
grant execute on function public.finish_digest(uuid, text[]) to service_role;
grant execute on function public.digest_off(uuid) to service_role;
grant execute on function public.check_job_token(text, text) to service_role;

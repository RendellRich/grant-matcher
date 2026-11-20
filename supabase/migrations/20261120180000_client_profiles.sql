-- Consultant client profiles. A Consultant account keeps up to 10 profiles (the limit trigger from the accounts
-- migration), each with its own saved profile and shortlist; Pro keeps one. Every function from
-- 20261120140000_saved_workspace.sql now takes the profile's id, and without one uses the account's first
-- profile, so a page that sends no id still works. A device remembers which client it last had open.

-- clock_timestamp, so two profiles made in one call (the first one and a new client) still sort in order.
alter table public.profiles add column created_at timestamptz not null default clock_timestamp();
alter table public.profiles add constraint profiles_label_set check (length(btrim(label)) > 0);

drop function public.my_workspace();
drop function public.save_profile(jsonb, real[]);
drop function public.save_shortlist(jsonb, bigint);
drop function private.workspace_profile(uuid);

-- The caller's account, or an error.
create or replace function private.my_account()
returns public.accounts language plpgsql stable security definer set search_path = '' as $$
declare
  acct public.accounts%rowtype;
begin
  select * into acct from public.accounts where owner = (select auth.uid());
  if not found then raise exception 'no account'; end if;
  return acct;
end;
$$;
revoke execute on function private.my_account() from public, anon, authenticated;

-- The profile to read or write: p_id when it is one of the account's, the first one when p_id is null
-- (made the first time). Raises unless the plan is paid; null when saving is off.
create or replace function private.workspace_profile(p_owner uuid, p_id uuid)
returns uuid language plpgsql security definer set search_path = '' as $$
declare
  acct public.accounts%rowtype;
  pid uuid;
begin
  select * into acct from public.accounts where owner = p_owner for update;
  if not found then raise exception 'no account'; end if;
  if not private.paid(acct.plan, acct.status) then raise exception 'Saving to your account comes with Pro.'; end if;
  if not acct.sync_on then return null; end if;
  if p_id is not null then
    select id into pid from public.profiles where id = p_id and account_id = acct.id;
    if pid is null then raise exception 'That client isn''t on this account.'; end if;
    return pid;
  end if;
  select id into pid from public.profiles where account_id = acct.id order by created_at, id limit 1;
  if pid is null then insert into public.profiles (account_id) values (acct.id) returning id into pid; end if;
  return pid;
end;
$$;
revoke execute on function private.workspace_profile(uuid, uuid) from public, anon, authenticated;

-- What the page loads: the plan, whether saving is on, the account's profiles (id and name), and the chosen
-- profile's saved profile and shortlist (p_id, or the first when p_id is null or not the account's).
create or replace function public.my_workspace(p_id uuid default null)
returns jsonb language sql stable security definer set search_path = '' as $$
  select coalesce((
    select jsonb_build_object('paid', private.paid(a.plan, a.status), 'plan', a.plan, 'on', a.sync_on,
      'profiles', coalesce((select jsonb_agg(jsonb_build_object('id', x.id, 'label', x.label) order by x.created_at, x.id)
        from public.profiles x where x.account_id = a.id), '[]'::jsonb),
      'id', p.id, 'profile', nullif(p.profile, '{}'::jsonb), 'vector', p.vector, 'updated_at', p.updated_at,
      'version', coalesce(p.shortlist_version, 0), 'shortlist', case when p.id is null then null else private.shortlist_of(p.id) end)
    from public.accounts a
    left join lateral (
      select * from public.profiles x where x.account_id = a.id
      order by (x.id = p_id) desc nulls last, x.created_at, x.id limit 1
    ) p on true
    where a.owner = (select auth.uid())), jsonb_build_object('paid', false, 'on', false));
$$;

create or replace function public.save_profile(p_profile jsonb, p_vector real[], p_id uuid default null)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  pid uuid;
begin
  if p_profile is null or jsonb_typeof(p_profile) <> 'object' or length(p_profile::text) > 20000 then
    raise exception 'Send a profile';
  end if;
  if p_vector is not null and array_length(p_vector, 1) <> 384 then raise exception 'Bad vector'; end if;
  pid := private.workspace_profile((select auth.uid()), p_id);
  if pid is null then return jsonb_build_object('ok', false, 'off', true); end if;
  update public.profiles set profile = p_profile, vector = p_vector, updated_at = now() where id = pid;
  return jsonb_build_object('ok', true, 'id', pid);
end;
$$;

create or replace function public.save_shortlist(p_items jsonb, p_base bigint, p_id uuid default null)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  pid uuid;
  ver bigint;
begin
  if p_items is null or jsonb_typeof(p_items) <> 'array' or jsonb_array_length(p_items) > 500 then
    raise exception 'Send a list';
  end if;
  pid := private.workspace_profile((select auth.uid()), p_id);
  if pid is null then return jsonb_build_object('ok', false, 'off', true); end if;
  select shortlist_version into ver from public.profiles where id = pid for update;
  if ver <> coalesce(p_base, -1) then
    return jsonb_build_object('ok', false, 'version', ver, 'shortlist', private.shortlist_of(pid));
  end if;
  delete from public.shortlist_items where profile_id = pid;
  insert into public.shortlist_items (profile_id, match_key, stage, own_deadline, stage_changed_at, updated_at, position, snapshot)
  select distinct on (e->>'key') pid, left(e->>'key', 200),
    case when e->>'stage' in ('applying', 'submitted') then e->>'stage' else 'saved' end,
    case when coalesce(e->>'due', '') ~ '^\d{4}-\d{2}-\d{2}$' then (e->>'due')::date end,
    case when coalesce(e->>'stageAt', '') ~ '^\d{4}-\d{2}-\d{2}T' then (e->>'stageAt')::timestamptz else now() end,
    case when coalesce(e->>'at', '') ~ '^\d{4}-\d{2}-\d{2}T' then (e->>'at')::timestamptz else now() end,
    n::int, e
  from jsonb_array_elements(p_items) with ordinality as x(e, n)
  where jsonb_typeof(e) = 'object' and coalesce(e->>'key', '') <> '' and length(e::text) <= 20000
  order by e->>'key', n;
  update public.profiles set shortlist_version = ver + 1 where id = pid;
  return jsonb_build_object('ok', true, 'version', ver + 1, 'id', pid);
end;
$$;

-- Adds a client profile (Consultant keeps up to 10; the limit trigger says so past that).
create or replace function public.add_client(p_label text)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  acct public.accounts%rowtype;
  pid uuid;
  name text := left(btrim(coalesce(p_label, '')), 120);
begin
  acct := private.my_account();
  if not private.paid(acct.plan, acct.status) then raise exception 'Client profiles come with Consultant.'; end if;
  if acct.plan <> 'consultant' then raise exception 'Client profiles come with Consultant.'; end if;
  if not acct.sync_on then raise exception 'Turn on saving to your account first.'; end if;
  if name = '' then raise exception 'Name the client.'; end if;
  perform private.workspace_profile(acct.owner, null); -- the first profile exists before a second is added
  insert into public.profiles (account_id, label) values (acct.id, name) returning id into pid;
  return jsonb_build_object('id', pid);
end;
$$;

create or replace function public.rename_client(p_id uuid, p_label text)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  acct public.accounts%rowtype;
  name text := left(btrim(coalesce(p_label, '')), 120);
begin
  acct := private.my_account();
  if name = '' then raise exception 'Name the client.'; end if;
  update public.profiles set label = name where id = p_id and account_id = acct.id;
  if not found then raise exception 'That client isn''t on this account.'; end if;
  return jsonb_build_object('ok', true);
end;
$$;

-- Deletes a client profile and its shortlist. The last profile stays.
create or replace function public.delete_client(p_id uuid)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  acct public.accounts%rowtype;
begin
  acct := private.my_account();
  if (select count(*) from public.profiles where account_id = acct.id) <= 1 then
    raise exception 'Keep at least one client.';
  end if;
  delete from public.profiles where id = p_id and account_id = acct.id;
  if not found then raise exception 'That client isn''t on this account.'; end if;
  return jsonb_build_object('ok', true);
end;
$$;

revoke execute on function public.my_workspace(uuid) from public, anon;
revoke execute on function public.save_profile(jsonb, real[], uuid) from public, anon;
revoke execute on function public.save_shortlist(jsonb, bigint, uuid) from public, anon;
revoke execute on function public.add_client(text) from public, anon;
revoke execute on function public.rename_client(uuid, text) from public, anon;
revoke execute on function public.delete_client(uuid) from public, anon;
grant execute on function public.my_workspace(uuid) to authenticated;
grant execute on function public.save_profile(jsonb, real[], uuid) to authenticated;
grant execute on function public.save_shortlist(jsonb, bigint, uuid) to authenticated;
grant execute on function public.add_client(text) to authenticated;
grant execute on function public.rename_client(uuid, text) to authenticated;
grant execute on function public.delete_client(uuid) to authenticated;

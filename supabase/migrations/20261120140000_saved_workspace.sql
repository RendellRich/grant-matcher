-- Profile and shortlist on any device (Pro and Consultant), in the profiles and shortlist_items tables the
-- accounts migration made. The page saves the profile it last searched with (and the mission vector its
-- browser made) and the whole shortlist; another device signed in to the same account loads them.
--
-- The shortlist is saved whole, with a version number on its profile. A save names the version it started
-- from; if another device saved in between, nothing is written and the saved copy comes back so the page can
-- merge the two and try again. Turning saving off deletes the saved profiles and shortlists; each browser
-- keeps its own copy. Pro keeps one profile; Consultant's client profiles will use the same tables.

alter table public.accounts add column sync_on boolean not null default true;
alter table public.profiles
  add column vector real[],
  add column shortlist_version bigint not null default 0,
  add constraint profiles_vector_len check (vector is null or array_length(vector, 1) = 384),
  add constraint profiles_profile_size check (length(profile::text) <= 20000);
alter table public.shortlist_items
  add column updated_at timestamptz not null default now(),
  add column position int not null default 0,
  add constraint shortlist_items_snapshot_size check (length(snapshot::text) <= 20000);

create or replace function private.paid(p_plan text, p_status text)
returns boolean language sql immutable set search_path = '' as $$
  select p_plan in ('pro', 'consultant') and p_status in ('active', 'trialing', 'past_due');
$$;
revoke execute on function private.paid(text, text) from public, anon, authenticated;

-- The saved items as the page stores them (the snapshot is the page's own item).
create or replace function private.shortlist_of(p_profile uuid)
returns jsonb language sql stable security definer set search_path = '' as $$
  select coalesce(jsonb_agg(s.snapshot order by s.position, s.match_key), '[]'::jsonb)
  from public.shortlist_items s where s.profile_id = p_profile;
$$;
revoke execute on function private.shortlist_of(uuid) from public, anon, authenticated;

-- What the page loads: whether saving is on, and the saved profile and shortlist.
create or replace function public.my_workspace()
returns jsonb language sql stable security definer set search_path = '' as $$
  select coalesce((
    select jsonb_build_object('paid', private.paid(a.plan, a.status), 'on', a.sync_on,
      'profile', p.profile, 'vector', p.vector, 'updated_at', p.updated_at,
      'version', coalesce(p.shortlist_version, 0), 'shortlist', case when p.id is null then null else private.shortlist_of(p.id) end)
    from public.accounts a
    left join lateral (select * from public.profiles x where x.account_id = a.id order by x.updated_at limit 1) p on true
    where a.owner = (select auth.uid())), jsonb_build_object('paid', false, 'on', false));
$$;

-- The account's profile row, made the first time. Raises unless the plan is paid.
create or replace function private.workspace_profile(p_owner uuid)
returns uuid language plpgsql security definer set search_path = '' as $$
declare
  acct public.accounts%rowtype;
  pid uuid;
begin
  select * into acct from public.accounts where owner = p_owner for update;
  if not found then raise exception 'no account'; end if;
  if not private.paid(acct.plan, acct.status) then raise exception 'Saving to your account comes with Pro.'; end if;
  if not acct.sync_on then return null; end if;
  select id into pid from public.profiles where account_id = acct.id order by updated_at limit 1;
  if pid is null then insert into public.profiles (account_id) values (acct.id) returning id into pid; end if;
  return pid;
end;
$$;
revoke execute on function private.workspace_profile(uuid) from public, anon, authenticated;

-- Saves the profile (the last save wins).
create or replace function public.save_profile(p_profile jsonb, p_vector real[])
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  pid uuid;
begin
  if p_profile is null or jsonb_typeof(p_profile) <> 'object' or length(p_profile::text) > 20000 then
    raise exception 'Send a profile';
  end if;
  if p_vector is not null and array_length(p_vector, 1) <> 384 then raise exception 'Bad vector'; end if;
  pid := private.workspace_profile((select auth.uid()));
  if pid is null then return jsonb_build_object('ok', false, 'off', true); end if;
  update public.profiles set profile = p_profile, vector = p_vector, updated_at = now() where id = pid;
  return jsonb_build_object('ok', true);
end;
$$;

-- Replaces the saved shortlist if p_base is still its version; otherwise returns the saved copy to merge with.
create or replace function public.save_shortlist(p_items jsonb, p_base bigint)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  pid uuid;
  ver bigint;
begin
  if p_items is null or jsonb_typeof(p_items) <> 'array' or jsonb_array_length(p_items) > 500 then
    raise exception 'Send a list';
  end if;
  pid := private.workspace_profile((select auth.uid()));
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
  return jsonb_build_object('ok', true, 'version', ver + 1);
end;
$$;

-- Turns saving on, or off (deleting the saved profiles and their shortlists).
create or replace function public.set_sync(p_on boolean)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  acct uuid;
begin
  select id into acct from public.accounts where owner = (select auth.uid());
  if acct is null then raise exception 'no account'; end if;
  update public.accounts set sync_on = p_on where id = acct;
  if not p_on then delete from public.profiles where account_id = acct; end if;
  return public.my_workspace();
end;
$$;

revoke execute on function public.my_workspace() from public, anon;
revoke execute on function public.save_profile(jsonb, real[]) from public, anon;
revoke execute on function public.save_shortlist(jsonb, bigint) from public, anon;
revoke execute on function public.set_sync(boolean) from public, anon;
grant execute on function public.my_workspace() to authenticated;
grant execute on function public.save_profile(jsonb, real[]) to authenticated;
grant execute on function public.save_shortlist(jsonb, bigint) to authenticated;
grant execute on function public.set_sync(boolean) to authenticated;

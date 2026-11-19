-- Stripe billing. stripe-webhook records each Stripe event it handles here, once, so a retried event isn't applied
-- twice, and refunds, disputes and fraud warnings are kept for review. Server-only: row level security on and no
-- policies, so only the service role reads or writes it.
create table public.billing_events (
  id text primary key,              -- Stripe event id (evt_...)
  type text not null,
  object_id text,                   -- the subscription, invoice, charge or session it was about
  note text not null default '',    -- what the webhook did: the plan it set, or "needs review"
  livemode boolean not null default false,
  received_at timestamptz not null default now()
);
alter table public.billing_events enable row level security;
revoke all on public.billing_events from anon, authenticated;
create index billing_events_review_idx on public.billing_events (received_at desc) where note = 'needs review';

-- One account per Stripe customer, and fast lookups from the webhook.
create unique index accounts_stripe_customer_idx on public.accounts (stripe_customer_id) where stripe_customer_id is not null;

-- A paid plan whose renewal just failed keeps working while Stripe retries the card (past_due); it drops to the
-- free view only when Stripe gives up and the subscription ends.
create or replace function public.record_search(p_sig text default null)
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
  paid := acct.plan in ('pro', 'consultant') and acct.status in ('active', 'trialing', 'past_due');
  if p_sig is not null then
    select exists (
      select 1 from public.search_log
      where account_id = acct.id and sig = p_sig and ran_at >= month_start
    ) into seen;
  end if;
  if not seen then
    insert into public.search_log (account_id, sig) values (acct.id, p_sig);
  end if;
  return jsonb_build_object('full', paid, 'plan', acct.plan, 'status', acct.status, 'repeat', seen);
end;
$$;
revoke execute on function public.record_search(text) from public, anon;
grant execute on function public.record_search(text) to authenticated;

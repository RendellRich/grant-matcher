-- While the server holds a Stripe test key, only accounts marked as testers may start a checkout, so nobody can
-- unlock a paid plan with Stripe's public test cards on the live site. Set by hand for the owner's own accounts.
alter table public.accounts add column billing_tester boolean not null default false;

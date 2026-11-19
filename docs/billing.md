# Billing, plans, the weekly email and deadline reminders

How paid plans work, where each piece lives, and how to take Grant Matcher from the Stripe sandbox to real payments.
Nothing secret is in this file or anywhere in the repository.

## The pieces

| Piece | Where | What it does |
| --- | --- | --- |
| Plans on the page | `web/src/app.tsx`, `web/src/access.ts` | Upgrade and Manage plan buttons, `?upgrade=pro` links, the note after checkout |
| `billing` function | `supabase/functions/billing` | Starts a Stripe Checkout for Pro or Consultant, or opens Stripe's billing portal |
| `stripe-webhook` function | `supabase/functions/stripe-webhook` | Checks Stripe's signature, then sets the account's plan from the subscription |
| Shared rules | `supabase/functions/_shared/billing-core.ts` | Lookup keys, which statuses count as paid, the founding coupon prefix (tested in `web/test/billing.test.ts`) |
| `weekly-email` function | `supabase/functions/weekly-email`, `web/src/server/digest.ts` | Emails each opted-in paid account its new strong matches once a week |
| `deadline-reminders` function | `supabase/functions/deadline-reminders`, `web/src/server/reminder-email.ts` | Emails each account with reminders on about shortlisted deadlines 14 and 3 days out |
| Email switches | `web/src/weekly.tsx` | Turns the weekly email and deadline reminders on or off; keeps the saved shortlist dates in step; the confirm-to-turn-off note |
| Database | `supabase/migrations/2026111920*`, `...21*`, `...22*`, `...23*` | `billing_events`, the tester flag, the weekly email columns and functions, the schedule |

The plan an account has is decided only by the webhook (or by hand in SQL for a free comp). The page never sets it.

## Secrets (Supabase, Edge Functions, Secrets)

| Name | Used by | Where it comes from |
| --- | --- | --- |
| `STRIPE_SECRET_KEY` | billing, stripe-webhook | A restricted key (see below). `rk_test_` while testing, `rk_live_` when live |
| `STRIPE_WEBHOOK_SECRET` | stripe-webhook | The webhook destination's signing secret (`whsec_`) |
| `RESEND_API_KEY` | weekly-email, deadline-reminders | Resend, API Keys, sending access for solutionsbyrich.com (key `grant-matcher-weekly-email`) |

Restricted key permissions: Write on Customers, Checkout Sessions and Customer portal; Read on Prices, Products and Subscriptions. Everything else None.
In the Dashboard this is Create secret key, Building your own integration, Custom permissions.

## Safety rules built in

- **Test key, tester accounts only.** While the key is a test key, `billing` lets only accounts with `billing_tester = true` check out. Everyone else sees "Paid plans aren't open yet", so nobody can unlock Pro with Stripe's public test cards.
- **Modes never mix.** The webhook ignores test events when the key is live, and live events when the key is a test key.
- **Each event once.** Webhook events are recorded in `billing_events` and a repeat is skipped. A failure returns 500 so Stripe retries.
- **Paid means** plan `pro` or `consultant` with status `active`, `trialing` or `past_due` (Stripe is still retrying). After the last failed retry Stripe cancels the subscription and the account goes back to Free.
- **The email jobs** authenticate with a token the database makes for itself (`private.job_tokens`). It is read at call time and never written anywhere.
- **Unsubscribe** needs a POST: the email's link opens the page, which asks for one press, so mail scanners that open links can't turn it off. Mail apps' one-click unsubscribe POSTs straight to the function.

## Stripe setup (sandbox, done)

- Products: Grant Matcher Pro ($39 a month, lookup key `gm_pro_monthly`) and Grant Matcher Consultant ($89 a month, lookup key `gm_consultant_monthly`, price switched off until its features exist). Tax behavior exclusive.
- Founding price: coupon `FOUNDING_PRO`, $10 off forever, 50 uses, Pro only. Promotion code `FOUNDING29`, new customers only.
- Billing portal: update card, invoices, name and address, cancel at period end with a reason. Plan switching off while one plan is for sale. Links to the Terms and Privacy pages.
- Webhook destination: `https://lthfecwgvpekrjjqszof.supabase.co/functions/v1/stripe-webhook` with the 9 events in `HANDLED_EVENTS`.
- Billing settings: Smart Retries (8 tries in 2 weeks), cancel after the last retry, emails for expiring cards, failed card payments and payments that need confirmation, receipts for payments and refunds.

## Going live

1. Finish Stripe's account activation (verify email, Activate Payments: the LLC's EIN, bank account, ID).
2. In live mode, repeat the sandbox setup above. Sandbox objects and settings don't carry over. The lookup keys must match exactly, because the code finds prices by them.
3. Make a live restricted key with the same permissions and replace `STRIPE_SECRET_KEY`.
4. Make the live webhook destination and replace `STRIPE_WEBHOOK_SECRET` with its signing secret.
5. Upload the policy pages (`/grant-matcher/terms/`, `/privacy/`, `/refunds/`) if they aren't live yet, and set them in Stripe's public business details.
6. Point the pricing page's Pro button at `https://rendellrich.github.io/grant-matcher/?upgrade=pro`. Keep Consultant on the waitlist until its features exist.
7. Buy Pro once with a real card on your own account, check the account switches to Pro, then refund it from the Dashboard.

## Everyday checks

- Recent webhook events: `select type, note, livemode, received_at from public.billing_events order by received_at desc limit 20;`
- Events that need a person (refunds, disputes, fraud warnings): `... where note = 'needs review'`.
- An account's plan: `select a.plan, a.status, a.founding, a.digest_on from public.accounts a join auth.users u on u.id = a.owner where u.email = '...';`
- Weekly email runs (every 10 minutes): `select status_code, content, created from net._http_response order by id desc limit 10;`
  - `not set up`: `RESEND_API_KEY` is missing.
  - `none due`: nobody is due this run.
  - `seeded`: someone just turned the email on; the first email comes a week later.
  - `sent N`: an email went out with N new matches.
  - `failed`: see the function's logs.
- Deadline reminder runs (every 10 minutes, 12:00 to 15:50 UTC): the same table. `none due` most of the time; `sent N` when N accounts got a reminder email.
- What an account has saved for reminders: `select key, due, stage, sent14, sent3 from public.reminders where account_id = '...';`
- Give a free comp: set `plan = 'consultant', status = 'active'` on the account. Test checkouts need `billing_tester = true`.

## Limits to know

- The weekly email sends one account per run, so about 1,000 a week. Process more per run before passing that.
- The first weekly email arrives a week after the email is turned on, and only if something new matched.
- An account whose plan ends keeps its weekly email profile and reminder dates saved but gets no emails until it pays again.
- Deadline reminders go out once each: the two-week one any morning from 14 days out to 4 days out, the three-day one from 3 days out to the day itself. A changed deadline starts both over. Submitted grants drop off.
- Reminders send up to 25 accounts per run, about 600 a morning.

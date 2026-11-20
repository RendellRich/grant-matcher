# Billing, plans, the weekly email and deadline reminders

How paid plans work, where each piece lives, and how it runs on real payments.
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
- **Your plan.** Paid accounts see how the plan is billed, what each payment costs after discounts and when it renews or ends. The page asks the billing function (`action: "status"`), which reads the subscription from Stripe each time (`planView` in `_shared/billing-core.ts`). The restricted key can't read coupons, so a founding coupon known only by its id counts as $10 off Pro ($20 off Consultant). A plan given by hand, with no subscription, shows as "at no charge".
- **Yearly.** The page sends `interval: "year"` (or the pricing page links `?upgrade=pro&interval=year`) and the function looks up the `_yearly` key instead of `_monthly`. Yearly checkouts take no promotion codes: the founding coupon is $10 off every invoice, which makes monthly $29 but would only take $10 off a year. The founding price is monthly only. Subscribers switch between monthly and yearly in the portal (see Live mode). A founding subscriber who switches to yearly keeps the $10 coupon, so pays $380 a year.
- **Modes never mix.** The webhook ignores test events when the key is live, and live events when the key is a test key.
- **Each event once.** Webhook events are recorded in `billing_events` and a repeat is skipped. A failure returns 500 so Stripe retries.
- **Paid means** plan `pro` or `consultant` with status `active`, `trialing` or `past_due` (Stripe is still retrying). After the last failed retry Stripe cancels the subscription and the account goes back to Free.
- **The email jobs** authenticate with a token the database makes for itself (`private.job_tokens`). It is read at call time and never written anywhere.
- **Unsubscribe** needs a POST: the email's link opens the page, which asks for one press, so mail scanners that open links can't turn it off. Mail apps' one-click unsubscribe POSTs straight to the function.

## Stripe setup (sandbox, done)

- Products: Grant Matcher Pro ($39 a month, lookup key `gm_pro_monthly`; $390 a year, lookup key `gm_pro_yearly`) and Grant Matcher Consultant ($89 a month, lookup key `gm_consultant_monthly`, price switched off until its features exist). Tax behavior exclusive.
- Founding price: coupon `FOUNDING_PRO`, $10 off forever, 50 uses, Pro only. Promotion code `FOUNDING29`, new customers only.
- Billing portal: update card, invoices, name and address, cancel at period end with a reason. Plan switching off while one plan is for sale. Links to the Terms and Privacy pages.
- Webhook destination: `https://lthfecwgvpekrjjqszof.supabase.co/functions/v1/stripe-webhook` with the 9 events in `HANDLED_EVENTS`.
- Billing settings: Smart Retries (8 tries in 2 weeks), cancel after the last retry, emails for expiring cards, failed card payments and payments that need confirmation, receipts for payments and refunds.

## Live mode (done, November 19, 2026)

Real payments are on. Stripe account: Solutions by Rich LLC (live, activated with the LLC's EIN). The sandbox stays as it was for testing.

- Products copied from the sandbox with Stripe's copy tool, same product IDs. The Pro price keeps lookup key `gm_pro_monthly`. Yearly Pro ($390, lookup key `gm_pro_yearly`) added November 20, 2026. Consultant ($89 a month, lookup key `gm_consultant_monthly`, `price_1UdztBIQhluXffqO6GZVMjSa`) added November 20, 2026, when its client profiles and emails went live.
- Founding prices: coupon `FOUNDING_PRO` ($10 off Pro forever, 50 uses, Pro only) with promotion code `FOUNDING29`, and coupon `FOUNDING_CONSULTANT` ($20 off Consultant forever, 50 uses, Consultant only) with promotion code `FOUNDING69`. Both codes are for first-time customers, 50 uses each. Each coupon applies only to its own product, so neither code works on the other plan.
- Billing portal: cancel at period end with a reason, update card, invoices, name and billing address. Email and phone changes off, so the Stripe email can't drift from the Grant Matcher sign-in. Plan switching on (November 20, 2026) between Pro monthly and Pro yearly: monthly to yearly applies at once, prorated and invoiced immediately; yearly to monthly applies when the paid year ends. No promotion codes or quantity changes in the portal.
- Public details: Terms and Privacy links, support email ren@solutionsbyrich.com. The phone number is not printed on receipts.
- Renewal reminders: on (November 20, 2026), 7 days before every renewal, monthly and yearly. Card-update links in all emails go to Stripe's hosted page (the legacy custom link to solutionsbyrich.com is gone and can't be restored). Emails include a link to the customer portal.
- Failed payments: retries on, the subscription cancels after the last one, failed-card and expiring-card emails with Stripe's hosted update page. Receipts for payments and refunds.
- Radar Lite (free). Stripe Tax off.
- Webhook destination `grant-matcher-supabase` (`we_1UdfHCIQhluXffqOVMC9TsGh`), same URL and the same 9 events.
- Restricted key `grant-matcher-live` (`rk_live_`), same permissions as above. Both live values are in the Supabase secrets.
- The pricing page at solutionsbyrich.com/grant-matcher sends Get Pro to `https://rendellrich.github.io/grant-matcher/?upgrade=pro`.

Checked: the live key creates live customers and checkout sessions. Not yet checked: the webhook signing secret. The first real sale proves it. If an event fails, Stripe retries for up to 3 days, so fix the secret and the account catches up on the next retry.

After the first sale, run the first query under Everyday checks and confirm a `checkout.session.completed` row with `livemode = true`, then check that account is `pro` and `founding`.

Stripe sign-in uses Google Authenticator for two-step. Keep the backup code somewhere safe. Without a working method you can't create keys or reveal secrets.

### Switching back to the sandbox

Put the `rk_test_` key and the sandbox webhook secret back in Supabase. Checkout then works only for accounts with `billing_tester = true`.

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
- Give a free comp: set `plan = 'consultant', status = 'active'` on the account.
- A `stripe_customer_id` saved while testing in the sandbox breaks checkout and the portal in live mode. Set it to null and the next checkout makes a live one.

## Limits to know

- The weekly email sends one account per run, so about 1,000 a week. Process more per run before passing that.
- The first weekly email arrives a week after the email is turned on, and only if something new matched.
- An account whose plan ends keeps its weekly email profile and reminder dates saved but gets no emails until it pays again.
- Deadline reminders go out once each: the two-week one any morning from 14 days out to 4 days out, the three-day one from 3 days out to the day itself. A changed deadline starts both over. Submitted grants drop off.
- Reminders send up to 25 accounts per run, about 600 a morning.

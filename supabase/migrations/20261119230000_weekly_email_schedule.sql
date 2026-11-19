-- Calls supabase/functions/weekly-email every ten minutes. Each call sends at most one account's email, and
-- returns at once when nobody is due. The job's token is read from private.job_tokens at call time, so it
-- never appears in the schedule or in any file.
create extension if not exists pg_net;
create extension if not exists pg_cron;
select cron.schedule('weekly-email', '*/10 * * * *', $$
  select net.http_post(
    url := 'https://lthfecwgvpekrjjqszof.supabase.co/functions/v1/weekly-email',
    headers := jsonb_build_object('Content-Type', 'application/json',
      'x-job-token', (select token::text from private.job_tokens where name = 'weekly-email')),
    body := '{}'::jsonb,
    timeout_milliseconds := 60000
  );
$$);

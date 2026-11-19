-- Sends deadline reminders every ten minutes from 12:00 to 15:50 UTC (about 8 to 11 am Eastern). Each call
-- sends up to 25 accounts' emails and returns at once when nothing is due.
select cron.schedule('deadline-reminders', '*/10 12-15 * * *', $$
  select net.http_post(
    url := 'https://lthfecwgvpekrjjqszof.supabase.co/functions/v1/deadline-reminders',
    headers := jsonb_build_object('Content-Type', 'application/json',
      'x-job-token', (select token::text from private.job_tokens where name = 'deadline-reminders')),
    body := '{}'::jsonb,
    timeout_milliseconds := 60000
  );
$$);

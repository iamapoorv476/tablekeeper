-- Run this once against your Supabase project before starting the dashboard.
-- It does two things the dashboard depends on:
--   1. lets the anon (browser) key read the three tables it displays
--   2. makes sure reservations changes actually stream over realtime

-- 1. Read access for the browser client.
-- These are display-only tables in a demo, so anon SELECT is fine. The agent
-- writes through the FastAPI backend using the service role, never from here.
alter table reservations enable row level security;
alter table tables       enable row level security;
alter table guests       enable row level security;

drop policy if exists "anon read reservations" on reservations;
create policy "anon read reservations" on reservations for select to anon using (true);

drop policy if exists "anon read tables" on tables;
create policy "anon read tables" on tables for select to anon using (true);

drop policy if exists "anon read guests" on guests;
create policy "anon read guests" on guests for select to anon using (true);

-- 2. Realtime. The publication add is idempotent-ish: it errors if the table
-- is already a member, which is harmless — that means it's already set up.
do $$
begin
  alter publication supabase_realtime add table reservations;
exception when duplicate_object then
  raise notice 'reservations already in supabase_realtime, skipping';
end $$;

-- UPDATE and DELETE events only carry the changed columns unless the table
-- publishes its full old row. The dashboard filters events by
-- reservation_date, so it needs that column present on every event.
alter table reservations replica identity full;
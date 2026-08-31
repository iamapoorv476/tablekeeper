-- The callback queue: the "no dead ends" path.
--
-- When the agent can't finish something on the call — a tool failed, the
-- request is out of scope, or the guest wants a human — it does NOT hang up
-- on a half-answer. It records what the guest actually wanted, with enough
-- context that a human can pick it up cold, and tells the guest someone will
-- call back. Every path ends with the guest handled.

create table if not exists callbacks (
  id uuid primary key default gen_random_uuid(),
  restaurant_id uuid references restaurants(id) on delete cascade,
  guest_id uuid references guests(id),
  caller_number text,
  guest_name text,
  reason text not null,        -- why the agent couldn't close it
  context text not null,       -- what the guest actually asked for
  vapi_call_id text,
  status text not null default 'open',   -- open | resolved
  created_at timestamptz default now(),
  resolved_at timestamptz
);

create index if not exists idx_callbacks_open
  on callbacks (restaurant_id, status, created_at desc);

alter table callbacks enable row level security;

drop policy if exists "anon read callbacks" on callbacks;
create policy "anon read callbacks" on callbacks for select to anon using (true);

-- The dashboard can close a callback. This is deliberate: it makes the
-- dashboard a second *writing* surface onto the same brain, not just a
-- viewer. Scoped to update only — the browser can never insert or delete.
drop policy if exists "anon resolve callbacks" on callbacks;
create policy "anon resolve callbacks" on callbacks for update to anon
  using (true) with check (true);

do $$
begin
  alter publication supabase_realtime add table callbacks;
exception when duplicate_object then
  raise notice 'callbacks already in supabase_realtime, skipping';
end $$;

alter table callbacks replica identity full;
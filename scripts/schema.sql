-- Voice Reservation Agent — shared "brain" schema
-- Run this against your Supabase Postgres (SQL editor or psql).

create extension if not exists pgcrypto;

create table if not exists restaurants (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  phone_number text,
  timezone text default 'Asia/Kolkata',
  opening_time time not null default '11:00',
  closing_time time not null default '23:00',
  created_at timestamptz default now()
);

create table if not exists house_rules (
  id uuid primary key default gen_random_uuid(),
  restaurant_id uuid references restaurants(id) on delete cascade,
  category text not null,        -- 'menu' | 'dietary' | 'policy'
  question_tags text[],          -- e.g. {'vegan','gluten-free'}
  content text not null,
  created_at timestamptz default now()
);

create table if not exists tables (
  id uuid primary key default gen_random_uuid(),
  restaurant_id uuid references restaurants(id) on delete cascade,
  label text not null,
  seats int not null,
  created_at timestamptz default now()
);

create table if not exists guests (
  id uuid primary key default gen_random_uuid(),
  restaurant_id uuid references restaurants(id) on delete cascade,
  phone_number text not null,
  name text,
  preferences text,
  created_at timestamptz default now(),
  unique (restaurant_id, phone_number)
);

create table if not exists reservations (
  id uuid primary key default gen_random_uuid(),
  restaurant_id uuid references restaurants(id) on delete cascade,
  table_id uuid references tables(id),
  guest_id uuid references guests(id),
  party_size int not null,
  reservation_date date not null,
  reservation_time time not null,
  duration_minutes int default 90,
  status text default 'confirmed',   -- confirmed | cancelled | modified
  source text default 'voice',       -- voice | dashboard | email
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists call_logs (
  id uuid primary key default gen_random_uuid(),
  vapi_call_id text,
  restaurant_id uuid references restaurants(id),
  caller_number text,
  started_at timestamptz,
  ended_at timestamptz,
  transcript jsonb,
  created_at timestamptz default now()
);

create table if not exists turn_logs (
  id uuid primary key default gen_random_uuid(),
  call_id uuid references call_logs(id) on delete cascade,
  turn_index int,
  role text,               -- 'user' | 'assistant' | 'tool'
  content text,
  tool_name text,
  latency_ms int,
  created_at timestamptz default now()
);

-- indexes that matter for the hot path (availability check runs on every call)
create index if not exists idx_reservations_slot
  on reservations (restaurant_id, reservation_date, reservation_time, status);
create index if not exists idx_reservations_table
  on reservations (table_id, reservation_date, status);
create index if not exists idx_guests_phone
  on guests (restaurant_id, phone_number);

-- enable realtime on the tables the dashboard needs to watch live
alter publication supabase_realtime add table reservations;
alter publication supabase_realtime add table call_logs;
# Basilico Trattoria — a voice agent and a shared brain

A phone number answers as a restaurant, books a table against real availability, and writes into
a Postgres database that a live dashboard is watching. The booking appears on screen while the
caller is still on the line, because both surfaces are reading and writing the same source of
truth — not two systems pretending to be one.

**Live:**
- Repo: [github.com/iamapoorv476/tablekeeper](https://github.com/iamapoorv476/tablekeeper)
- Call it: **+1 (504) 588-6285**
- Watch it: [tablekeeper-three.vercel.app/dashboard](https://tablekeeper-three.vercel.app/dashboard)
- Backend: [tablekeeper-production-4a7b.up.railway.app](https://tablekeeper-production-4a7b.up.railway.app/health)

Built as a demo for **Elyra** (an AI reservation platform for restaurants built around exactly
this idea — one shared brain across voice, email, and booking), and doubles as a demo for
**Feather** (enterprise voice/text/email agents) and **Cekura** (voice agent testing and
observability).

---

## What happens during a call

1. **The phone rings.** A voice agent (Vapi + Claude Haiku + Deepgram) picks up as the
   restaurant. It looks up the caller's number and greets returning guests by name.
2. **It checks the floor.** Before promising anything, it queries real table capacity for the
   requested slot inside a single database round trip, and offers genuinely-free alternatives
   when nothing fits.
3. **It writes to Postgres.** The booking is committed inside a transaction that re-checks
   availability at write time, so two callers can't take the same table.
4. **The floor sees it.** The change streams to the dashboard over Supabase's Postgres
   replication — no polling, no refresh. The row lands while the caller is still talking.
5. **If it can't help, it says so.** Out-of-scope requests, failed lookups, and anything the
   agent can't resolve get logged as a callback with full context, instead of a dead end or an
   invented answer.

---

## Architecture

```
┌─────────────┐      ┌──────────────┐      ┌─────────────────┐
│  Phone call  │─────▶│     Vapi      │─────▶│  FastAPI backend │
│  (caller)    │      │ (STT/TTS/LLM) │      │    (Railway)     │
└─────────────┘      └──────────────┘      └────────┬─────────┘
                                                       │ writes
                                                       ▼
                                             ┌───────────────────┐
                                             │  Supabase Postgres │
                                             │  (the shared brain)│
                                             └─────────┬─────────┘
                                                        │ realtime
                                                        ▼
                                             ┌───────────────────┐
                                             │  Next.js dashboard │
                                             │     (Vercel)       │
                                             └───────────────────┘
```

The backend and the dashboard never talk to each other directly. They both talk to the same
database — that's the whole point. A phone booking and a dashboard click are two writers on one
table, not two systems synchronized after the fact.

---

## Stack

| Layer | Choice |
|---|---|
| Voice | Vapi — Claude Haiku 4.5, Deepgram Nova-2 (transcription), Deepgram Aura / Azure Neural (voice) |
| Backend | FastAPI + asyncpg, deployed on Railway |
| Database | Postgres via Supabase, with Row Level Security and realtime replication |
| Dashboard | Next.js 14 + Tailwind, deployed on Vercel, Supabase realtime subscriptions |
| Testing | A 9-case eval harness hitting the real webhook contract |

---

## Schema

Six tables, one shared brain:

```
restaurants   — name, hours, timezone
tables        — label, seat count
guests        — phone number, name, preferences (grows over calls)
reservations  — party size, date, time, table, guest_name, source (voice/dashboard)
call_logs     — one row per real call
callbacks     — requests the agent couldn't close, for a human to pick up
```

`guest_name` is stored directly on the reservation, not only inferred through a linked guest
record — see [What broke and what it taught me](#what-broke-and-what-it-taught-me) for why that
turned out to matter.

Full DDL: [`scripts/schema.sql`](scripts/schema.sql),
[`scripts/callbacks_setup.sql`](scripts/callbacks_setup.sql).

---

## The five tools

The agent has five tool calls available, each a thin FastAPI endpoint behind one webhook
(`/vapi/tools`):

| Tool | Does |
|---|---|
| `lookup_guest` | Recognizes a returning caller by phone number, surfaces their name and preferences |
| `check_availability` | Finds the smallest table that fits the party, or the nearest real alternative |
| `create_reservation` | Books it — re-checks availability inside the write transaction, so a slot that filled a second earlier can't be double-booked |
| `modify_reservation` | Changes an existing booking, resolved by caller ID |
| `request_callback` | Logs anything the agent can't close — out of scope, failed twice, or the caller asks for a human — with enough context for a person to pick it up cold |

Every failure response carries a `next_step` field that tells the model exactly how to recover,
rather than leaving it to improvise. This exists because of a real bug — see below.

---

## What broke and what it taught me

This project was built end to end over several real debugging sessions, against a real phone
number, with real minutes spent. Here's what actually went wrong, because a system that never
broke either wasn't tested hard enough or isn't being honestly described.

**The agent lied about a modification.** Early on, the caller asked to move a booking to 7 PM.
The agent said *"your reservation has been updated to 7 PM."* The database still said 8 PM. The
tool had correctly failed to resolve the reservation — the model just narrated success anyway.
Fixed two ways: every failure response now includes an explicit `next_step` instruction telling
the model how to recover, and the system prompt has a hard rule — never claim success unless the
tool's own response says `"success": true`. Verified with a regression test
(`case_modify_never_claims_false_success`).

**Bookings showed up as "Walk-in."** `create_reservation` only linked a guest record when a
caller number was present. Any call without one (every web test call, and any real call where the
lookup failed) lost the name entirely, even though the caller had clearly given it. Fixed by
storing `guest_name` directly on the reservation, independent of whether guest-linking succeeds.

**The availability search cost up to 6 sequential database round trips.** `find_alternatives`
called the single-slot check once per candidate time — a network round trip each, back to back.
Rewrote it to fetch the day's reservations once and evaluate every candidate in memory: measured
6 round trips down to 1 on a warm cache. Verified against the eval suite with no regression.
Real-world latency impact on the deployed system wasn't cleanly isolated — see
[Latency](#latency) below for why, and what that itself revealed.

**The assistant went stale the day after it was created.** "Today's date" was computed once in
Python and baked into the system prompt at creation time. A booking made for "today" three days
later landed on the wrong date, because the assistant's only reference for "today" was frozen in
the past. Fixed with Vapi's `{{"now" | date: ...}}` dynamic variable, resolved fresh by Vapi on
every call instead of once at creation.

**Windows broke `strftime` twice, in two different ways.** `%-I` (no leading zero) is a Linux/Mac
extension that doesn't exist on Windows. Then, on the Microsoft Store Python distribution
specifically, even the *standard* `%I` failed with the same error — traced to that distribution's
sandboxed C runtime breaking locale-dependent calls. Fixed by computing 12-hour time and AM/PM
with plain arithmetic instead of `strftime` at all, which can't break this way on any platform.

**Supabase's direct connection string is IPv6-only, and that broke twice in two different
places** — once on a home network that couldn't route to it, once on Railway, whose containers
only have IPv4 egress. Both times the fix was switching to Supabase's Session Pooler connection
string, which is IPv4-reachable.

**Vapi's tool-calling API shape didn't match what the docs implied.** Tools have to be created
via a separate `/tool` endpoint and referenced by ID (`model.toolIds`) — embedding them inline is
rejected. And the webhook's actual `toolCallList` payload carries `name`/`arguments` directly, not
nested under a `function` key as in classic OpenAI-style function calling. Found by inspecting a
real webhook payload rather than trusting an assumption.

Each of these is a regression test now. See [`scripts/eval_harness.py`](scripts/eval_harness.py).

---

## Eval suite

9 cases, each one a regression test for a real bug found above, run against the actual
`/vapi/tools` webhook rather than a mock:

| Case | Result |
|---|---|
| Books into the smallest table that fits | ✓ pass |
| Falls back to a larger table once small ones are full | ✓ pass |
| Alternatives offered when full are actually free | ✓ pass |
| `create_reservation` re-checks availability, refuses a stale slot | ✓ pass |
| `modify_reservation` never claims success when it can't resolve the booking | ✓ pass |
| `modify_reservation` updates the slot without losing the guest's name | ✓ pass |
| `request_callback` auto-links an existing guest by phone number | ✓ pass |
| Party bigger than any table returns unavailable, never a fake fit | ✓ pass |
| A malformed tool call doesn't break other calls in the same batch | ✓ pass |

**9/9**, run against the live Supabase database. Every case is isolated to a sandboxed future
date (`2099-06-15`) so it never touches real service data, and cleans up after itself regardless
of pass or fail.

```bash
cd scripts
export DATABASE_URL="..."      # same as backend/.env
export BACKEND_URL="https://tablekeeper-production-4a7b.up.railway.app"
python eval_harness.py
```

---

## Latency

Backend-side tool execution, measured by the server's own instrumentation, is fast:
**220–930ms** per call, consistently, including on the deployed Railway instance.

The full round-trip latency Vapi reports end to end is higher — median ~2s, p95 in the 7–8s
range across real calls. Tracing this down against the server's own logs showed the backend was
never the bottleneck: the gap is dominated by LLM reasoning time and Vapi's own orchestration
layer, not the database. That's a more useful finding than a clean before/after number would have
been — it means the round-trip optimization below is real and verified, but isn't the lever that
would move the number a caller actually experiences. The next real lever is turn-level latency in
the voice pipeline itself (model choice, streaming), not the tool layer.

**What was optimized, and measured:**
- `find_alternatives`: up to 6 sequential DB round trips → 1, by fetching the day's data once and
  evaluating every candidate slot in memory instead of one query per candidate
- `get_or_create_guest`: 2 round trips (a SELECT the INSERT's own `ON CONFLICT` made redundant) → 1

Both measured directly (query-count instrumentation, not estimated), both verified against the
full eval suite with no regression.

```bash
export VAPI_API_KEY="..."
python scripts/latency_report.py
```

---

## Multilingual: Swedish variant

Elyra's customer base is almost entirely Stockholm restaurants, so a second assistant variant
exists with the spoken content translated to Swedish (Azure `sv-SE-SofieNeural` voice, Deepgram
`sv` transcription) while the tool-calling instructions stay in English — Claude follows English
instructions reliably regardless of what language it's told to speak, and translating conditional
logic risked introducing subtle errors for no benefit, since the caller never sees that part of
the prompt.

Verified over a real phone call: natural voice quality confirmed by ear, fluent and grammatically
correct responses throughout, and `lookup_guest` firing correctly mid-Swedish-conversation —
proof the tool layer is identical regardless of language. A full Swedish booking wasn't completed
in testing, since verifying it meant speaking real Swedish, which I don't; that's a testing gap,
not a system limitation, and worth being explicit about rather than overstating.

```bash
export LANGUAGE=sv
python scripts/create_assistant.py
```

---

## Known limitations

Being direct about what isn't finished:

- **`DEFAULT_RESTAURANT_ID` is hardcoded** despite the schema being fully multi-tenant. A
  deliberate scoping choice for a single-restaurant demo, not an oversight — threading a real
  restaurant ID through every call is the natural next step for multi-tenant use.
- **`turn_logs` exists in the schema and nothing writes to it yet.** Per-tool latency currently
  only goes to stdout logging and Vapi's own call history, not the database. The table is there
  for a future self-hosted latency pipeline.
- **The dashboard has no automated tests.** The backend has nine; the frontend has none. Verified
  manually and repeatedly against real calls, but not regression-tested.
- **The Swedish variant's dynamic-date fix and full booking flow aren't independently verified in
  Swedish** — see above.

---

## Setup

**1. Database**
```bash
psql "$DATABASE_URL" -f scripts/schema.sql
psql "$DATABASE_URL" -f scripts/callbacks_setup.sql
psql "$DATABASE_URL" -f scripts/seed.sql
psql "$DATABASE_URL" -f scripts/dashboard_setup.sql
```

**2. Backend**
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env   # fill in DATABASE_URL (Supabase Session Pooler, not Direct Connection)
uvicorn app.main:app --reload --port 8001
```

**3. Dashboard**
```bash
cd dashboard
npm install
cp .env.local.example .env.local   # fill in Supabase URL + anon key
npm run dev
```

**4. Voice agent**
```bash
cd scripts
export VAPI_API_KEY="..."
export SERVER_URL="https://your-deployed-backend/vapi/tools"
python create_assistant.py
```
Assign the printed assistant ID to a Vapi phone number.

---

## Repo structure

```
backend/
  app/
    routes/vapi_tools.py       — the single webhook, dispatches by tool name
    services/
      availability.py          — table-fit + alternatives search
      reservations.py          — create/modify, transactional race guard
      guests.py                — lookup + upsert
      callbacks.py             — the no-dead-ends path
dashboard/
  app/
    page.tsx                   — landing page
    dashboard/page.tsx         — the live service sheet
  components/
    ReservationRail.tsx        — the timeline, with the live-arrival animation
    FloorMap.tsx                — table occupancy at a glance
    CallbackQueue.tsx           — what needs a human
scripts/
  schema.sql, seed.sql, callbacks_setup.sql, dashboard_setup.sql
  create_assistant.py           — builds the Vapi assistant + tools
  eval_harness.py                — 9-case regression suite
  latency_report.py              — pulls real per-tool timing from Vapi
```

---

Built with Claude, Vapi, Supabase, and a working phone number.

[github.com/iamapoorv476/tablekeeper](https://github.com/iamapoorv476/tablekeeper)

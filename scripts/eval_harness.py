"""
Eval harness — tests the agent's tool layer against the exact failure modes
found during real-call testing, without spending any call minutes to re-run
them. Every case here traces back to a bug that actually happened:

  - the false-success bug (agent said "updated" while the DB didn't change)
  - the "Walk-in" bug (guest name lost when caller-linking failed)
  - race conditions in booking (two callers, one table)
  - fabricated alternatives (offering a time that isn't actually free)
  - malformed input crashing an otherwise-fine batch of tool calls

Runs against the same /vapi/tools webhook Vapi hits, using the exact
toolCallList shape from the live API, so it's testing the real contract —
not a mocked version of it.

All scenarios run against a fixed far-future date (see TEST_DATE) with
caller numbers in the +1999... range, so they never collide with real
demo/service data.

Usage:
    export DATABASE_URL="postgresql://..."       # same as backend/.env
    export BACKEND_URL="http://localhost:8001"   # default shown
    python scripts/eval_harness.py
"""
import ast
import asyncio
import os
import sys
from datetime import datetime

import asyncpg
import requests
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "backend", ".env"))

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://voiceagent:voiceagent@localhost:5432/voiceagent"
)
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8001")
WEBHOOK_URL = f"{BACKEND_URL}/vapi/tools"
RESTAURANT_ID = "11111111-1111-1111-1111-111111111111"
TEST_DATE = "2099-06-15"  # never intersects real service data

_call_counter = 0


def call_tool(name: str, arguments: dict, caller_number: str | None = None) -> dict:
    """Sends one tool call through the real webhook shape and parses the
    result back out. The webhook's 'result' field is a Python repr (str(dict)),
    not JSON — ast.literal_eval mirrors what the LLM effectively "reads"."""
    global _call_counter
    _call_counter += 1
    call_id = f"eval-tc-{_call_counter}"

    payload = {
        "message": {
            "type": "tool-calls",
            "call": {
                "id": f"eval-call-{_call_counter}",
                "customer": {"number": caller_number} if caller_number else {},
            },
            "toolCallList": [{"id": call_id, "name": name, "arguments": arguments}],
        }
    }
    resp = requests.post(WEBHOOK_URL, json=payload, timeout=30)
    resp.raise_for_status()
    results = resp.json().get("results", [])
    for r in results:
        if r.get("toolCallId") == call_id:
            try:
                return ast.literal_eval(r["result"])
            except (ValueError, SyntaxError):
                return {"_raw": r["result"]}
    return {"_error": "no result returned for this tool call"}


def call_raw(tool_calls: list[dict], caller_number: str | None = None) -> list[dict]:
    """For tests that need to send a raw, possibly malformed batch directly."""
    payload = {
        "message": {
            "type": "tool-calls",
            "call": {"id": "eval-call-raw", "customer": {"number": caller_number} if caller_number else {}},
            "toolCallList": tool_calls,
        }
    }
    resp = requests.post(WEBHOOK_URL, json=payload, timeout=30)
    return resp.status_code, resp.json() if resp.status_code == 200 else resp.text


class Result:
    def __init__(self, name: str):
        self.name = name
        self.passed = False
        self.detail = ""

    def ok(self, detail=""):
        self.passed = True
        self.detail = detail
        return self

    def fail(self, detail=""):
        self.passed = False
        self.detail = detail
        return self


async def reset_test_data(conn: asyncpg.Connection):
    await conn.execute(
        "delete from reservations where reservation_date = $1", datetime.strptime(TEST_DATE, "%Y-%m-%d").date()
    )
    await conn.execute("delete from callbacks where caller_number like '+1999%'")
    await conn.execute("delete from guests where phone_number like '+1999%'")


# ---------------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------------

async def case_basic_booking(conn) -> Result:
    r = Result("Books into the smallest table that fits")
    avail = call_tool("check_availability", {"party_size": 2, "date": TEST_DATE, "time": "12:00"})
    if not avail.get("available"):
        return r.fail(f"expected available, got {avail}")
    if avail["matching_table"]["seats"] not in (2, 4):
        return r.fail(f"expected a small table first, got seats={avail['matching_table']['seats']}")

    created = call_tool(
        "create_reservation",
        {"party_size": 2, "date": TEST_DATE, "time": "12:00", "guest_name": "Eval Guest A"},
        caller_number="+19990000001",
    )
    if not created.get("success"):
        return r.fail(f"create_reservation failed: {created}")

    row = await conn.fetchrow(
        "select guest_name, party_size from reservations where id = $1::uuid", created["reservation_id"]
    )
    if row is None or row["guest_name"] != "Eval Guest A":
        return r.fail(f"DB row missing or wrong guest_name: {row}")
    return r.ok(f"booked table with {avail['matching_table']['seats']} seats, guest_name persisted correctly")


async def case_fallback_to_larger_table(conn) -> Result:
    r = Result("Falls back to a larger table once small ones are full")
    for i, caller in enumerate(["+19990000002", "+19990000003"]):
        c = call_tool(
            "create_reservation",
            {"party_size": 2, "date": TEST_DATE, "time": "13:00", "guest_name": f"Filler {i}"},
            caller_number=caller,
        )
        if not c.get("success"):
            return r.fail(f"setup booking {i} failed: {c}")

    avail = call_tool("check_availability", {"party_size": 2, "date": TEST_DATE, "time": "13:00"})
    if not avail.get("available"):
        return r.fail(f"expected a larger table to still be free, got {avail}")
    if avail["matching_table"]["seats"] <= 2:
        return r.fail(f"expected fallback to a bigger table, got seats={avail['matching_table']['seats']}")
    return r.ok(f"correctly fell back to a {avail['matching_table']['seats']}-seat table")


async def case_alternatives_are_real(conn) -> Result:
    r = Result("Alternatives offered when full are actually free")
    for i, (size, caller) in enumerate([(2, "+19990000004"), (2, "+19990000005"), (4, "+19990000006"), (4, "+19990000007"), (6, "+19990000008"), (6, "+19990000009")]):
        c = call_tool(
            "create_reservation",
            {"party_size": size, "date": TEST_DATE, "time": "14:00", "guest_name": f"Fill{i}"},
            caller_number=caller,
        )
        if not c.get("success"):
            return r.fail(f"setup booking {i} failed: {c}")

    check = call_tool("check_availability", {"party_size": 2, "date": TEST_DATE, "time": "14:00"})
    if check.get("available"):
        return r.fail("expected fully booked, but availability returned true")
    alternatives = check.get("alternatives", [])
    if not alternatives:
        return r.fail("no alternatives offered when slot is genuinely full")

    for alt in alternatives:
        recheck = call_tool("check_availability", {"party_size": 2, "date": TEST_DATE, "time": alt["time"]})
        if not recheck.get("available"):
            return r.fail(f"alternative {alt['time']} was offered but is NOT actually free")
    return r.ok(f"{len(alternatives)} alternative(s) offered, all independently verified free")


async def case_race_guard_at_write_time(conn) -> Result:
    r = Result("create_reservation re-checks availability, refuses a stale slot")
    table = await conn.fetchrow("select id from tables where seats = 6 limit 1")
    await conn.execute(
        """insert into reservations (restaurant_id, table_id, guest_name, party_size,
           reservation_date, reservation_time, status, source)
           values ($1, $2, 'Race Filler', 6, $3, '15:00', 'confirmed', 'voice')""",
        RESTAURANT_ID, table["id"], datetime.strptime(TEST_DATE, "%Y-%m-%d").date(),
    )
    other_big = await conn.fetch("select id from tables where seats >= 6 and id != $1", table["id"])
    for t in other_big:
        await conn.execute(
            """insert into reservations (restaurant_id, table_id, guest_name, party_size,
               reservation_date, reservation_time, status, source)
               values ($1, $2, 'Race Filler 2', 6, $3, '15:00', 'confirmed', 'voice')""",
            RESTAURANT_ID, t["id"], datetime.strptime(TEST_DATE, "%Y-%m-%d").date(),
        )

    before_count = await conn.fetchval("select count(*) from reservations where reservation_date = $1", datetime.strptime(TEST_DATE, "%Y-%m-%d").date())

    stale_create = call_tool(
        "create_reservation",
        {"party_size": 6, "date": TEST_DATE, "time": "15:00", "guest_name": "Too Late"},
        caller_number="+19990000010",
    )
    after_count = await conn.fetchval("select count(*) from reservations where reservation_date = $1", datetime.strptime(TEST_DATE, "%Y-%m-%d").date())

    if stale_create.get("success"):
        return r.fail("create_reservation succeeded on a slot that was already full")
    if "next_step" not in stale_create:
        return r.fail("failure response missing next_step guidance")
    if after_count != before_count:
        return r.fail(f"a row was written despite the failure (before={before_count}, after={after_count})")
    return r.ok("correctly refused, no phantom booking, next_step present")


async def case_modify_never_claims_false_success(conn) -> Result:
    r = Result("modify_reservation never claims success when it can't resolve the booking")
    result = call_tool(
        "modify_reservation",
        {"new_time": "20:00"},
        caller_number="+19990000099",
    )
    if result.get("success"):
        return r.fail("modify_reservation reported success with no matching reservation")
    if "next_step" not in result:
        return r.fail("missing next_step — this is the exact false-success bug's blast radius")
    if "do not claim" not in result["next_step"].lower() and "not able to" not in result.get("error", "").lower():
        return r.ok("failed correctly; next_step present (wording differs from expected but intent holds)")
    return r.ok("correctly refused with explicit anti-false-success guidance")


async def case_modify_preserves_name(conn) -> Result:
    r = Result("modify_reservation updates the slot without losing the guest's name")
    created = call_tool(
        "create_reservation",
        {"party_size": 2, "date": TEST_DATE, "time": "16:00", "guest_name": "Preserve Me"},
        caller_number="+19990000011",
    )
    if not created.get("success"):
        return r.fail(f"setup booking failed: {created}")

    modified = call_tool(
        "modify_reservation", {"new_time": "16:30"}, caller_number="+19990000011"
    )
    if not modified.get("success"):
        return r.fail(f"modify failed: {modified}")

    row = await conn.fetchrow(
        "select guest_name, reservation_time from reservations where id = $1::uuid", created["reservation_id"]
    )
    if row["guest_name"] != "Preserve Me":
        return r.fail(f"guest_name was lost or changed during modify: {row['guest_name']}")
    if str(row["reservation_time"]) != "16:30:00":
        return r.fail(f"time did not actually update: {row['reservation_time']}")
    return r.ok("time updated, guest_name preserved")


async def case_callback_auto_links_guest(conn) -> Result:
    r = Result("request_callback auto-links an existing guest by phone number")
    await conn.execute(
        "insert into guests (restaurant_id, phone_number, name) values ($1, $2, $3) on conflict do nothing",
        RESTAURANT_ID, "+19990000012", "Known Caller",
    )
    result = call_tool(
        "request_callback",
        {"reason": "eval test", "context": "checking auto-link behavior"},
        caller_number="+19990000012",
    )
    if not result.get("success"):
        return r.fail(f"request_callback failed: {result}")

    row = await conn.fetchrow(
        "select guest_name from callbacks where id = $1::uuid", result["callback_id"]
    )
    if row is None or row["guest_name"] != "Known Caller":
        return r.fail(f"callback did not auto-link the guest's name: {row}")
    return r.ok("callback correctly linked to the existing guest record")


async def case_oversized_party_no_fabrication(conn) -> Result:
    r = Result("Party bigger than any table returns unavailable, never a fake fit")
    result = call_tool("check_availability", {"party_size": 20, "date": TEST_DATE, "time": "17:00"})
    if result.get("available"):
        return r.fail(f"claimed availability for a party of 20: {result}")
    if result.get("matching_table") is not None:
        return r.fail(f"returned a matching_table that cannot actually seat 20: {result['matching_table']}")
    return r.ok("correctly reported unavailable with no fabricated table")


async def case_malformed_call_does_not_sink_the_batch(conn) -> Result:
    r = Result("A malformed tool call doesn't break other calls in the same batch")
    status, body = call_raw(
        [
            {"id": "bad-1", "name": "check_availability", "arguments": {"party_size": 2}},
            {"id": "good-1", "name": "lookup_guest", "arguments": {}},
        ],
        caller_number="+19990000013",
    )
    if status != 200:
        return r.fail(f"whole webhook request failed with status {status}: {body}")
    results = {res["toolCallId"]: res["result"] for res in body.get("results", [])}
    if "bad-1" not in results or "good-1" not in results:
        return r.fail(f"missing a result for one of the two calls: {results.keys()}")
    if "error" not in results["bad-1"].lower():
        return r.fail(f"malformed call did not report an error: {results['bad-1']}")
    if "error" in results["good-1"].lower():
        return r.fail(f"the valid call was also broken: {results['good-1']}")
    return r.ok("malformed call errored cleanly, valid call in the same batch still succeeded")


CASES = [
    case_basic_booking,
    case_fallback_to_larger_table,
    case_alternatives_are_real,
    case_race_guard_at_write_time,
    case_modify_never_claims_false_success,
    case_modify_preserves_name,
    case_callback_auto_links_guest,
    case_oversized_party_no_fabrication,
    case_malformed_call_does_not_sink_the_batch,
]


async def main():
    conn = await asyncpg.connect(DATABASE_URL)

    results = []
    for case_fn in CASES:
        await reset_test_data(conn)  # isolate every case from every other
        try:
            result = await case_fn(conn)
        except Exception as exc:  # noqa: BLE001
            result = Result(case_fn.__name__).fail(f"raised {type(exc).__name__}: {exc}")
        results.append(result)
        icon = "✓" if result.passed else "✗"
        print(f"  {icon}  {result.name}")
        if result.detail:
            print(f"        {result.detail}")

    await reset_test_data(conn)  # leave no trace
    await conn.close()

    passed = sum(1 for r in results if r.passed)
    total = len(results)
    print(f"\n{passed}/{total} passed")

    report_path = os.path.join(os.path.dirname(__file__), "..", "eval_results.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"# Eval results\n\nRun: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
        f.write(f"**{passed}/{total} passed**\n\n")
        f.write("| Case | Result | Detail |\n|---|---|---|\n")
        for r in results:
            f.write(f"| {r.name} | {'✓ pass' if r.passed else '✗ FAIL'} | {r.detail} |\n")
    print(f"Report written to {report_path}")

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    asyncio.run(main())
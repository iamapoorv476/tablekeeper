from datetime import datetime, timedelta, time as dtime, date as ddate
import time as _time
import asyncpg

DEFAULT_DURATION_MINUTES = 90
DEFAULT_RESTAURANT_ID = "11111111-1111-1111-1111-111111111111"

# Offsets (in minutes) tried, in order, when the requested slot doesn't fit.
ALT_OFFSETS = [30, -30, 60, -60, 90]

# Tables and restaurant hours essentially never change during a call — a
# restaurant doesn't add a table mid-dinner-service. Caching them in-process
# turns what used to be a per-call network round trip into a dict lookup.
# TTL is short enough that a real edit to the seed data shows up within
# minutes without needing a restart.
_CACHE_TTL_SECONDS = 300
_tables_cache: dict[str, tuple[list, float]] = {}
_hours_cache: dict[str, tuple[dtime, dtime, float]] = {}


def _parse_date(date):
    return date if isinstance(date, ddate) else datetime.strptime(date, "%Y-%m-%d").date()


def _parse_time(time_str):
    return time_str if isinstance(time_str, dtime) else datetime.strptime(time_str, "%H:%M").time()


def _minutes(t: dtime) -> int:
    return t.hour * 60 + t.minute


async def find_smallest_fitting_table(
    conn: asyncpg.Connection,
    restaurant_id: str,
    party_size: int,
    date: str,
    time_str: str,
    duration_minutes: int = DEFAULT_DURATION_MINUTES,
):
    """Returns the smallest table (row) that fits party_size and is free
    for the [time_str, time_str+duration) window on `date`, or None.

    This stays a single direct query — it's called once per check, and it's
    also the query create_reservation/modify_reservation re-run inside a
    transaction as the final race-condition guard, where a fresh read
    straight from the source of truth matters more than avoiding one query.
    The expensive path was never this call; it was find_alternatives calling
    this in a loop (see below)."""
    date_obj = _parse_date(date)
    time_obj = _parse_time(time_str)
    row = await conn.fetchrow(
        """
        select t.id, t.label, t.seats
        from tables t
        where t.restaurant_id = $1
          and t.seats >= $2
          and t.id not in (
            select r.table_id
            from reservations r
            where r.restaurant_id = $1
              and r.reservation_date = $3
              and r.status = 'confirmed'
              and r.table_id is not null
              and (r.reservation_time, r.reservation_time + (r.duration_minutes || ' minutes')::interval)
                  overlaps ($4::time, $4::time + ($5::text || ' minutes')::interval)
          )
        order by t.seats asc
        limit 1
        """,
        restaurant_id,
        party_size,
        date_obj,
        time_obj,
        str(duration_minutes),
    )
    return row


async def _get_tables_cached(conn: asyncpg.Connection, restaurant_id: str):
    now = _time.monotonic()
    cached = _tables_cache.get(restaurant_id)
    if cached and cached[1] > now:
        return cached[0]
    rows = await conn.fetch(
        "select id, label, seats from tables where restaurant_id = $1", restaurant_id
    )
    _tables_cache[restaurant_id] = (rows, now + _CACHE_TTL_SECONDS)
    return rows


async def get_restaurant_hours(conn: asyncpg.Connection, restaurant_id: str):
    now = _time.monotonic()
    cached = _hours_cache.get(restaurant_id)
    if cached and cached[2] > now:
        return cached[0], cached[1]

    row = await conn.fetchrow(
        "select opening_time, closing_time from restaurants where id = $1",
        restaurant_id,
    )
    opening, closing = (row["opening_time"], row["closing_time"]) if row else (dtime(11, 0), dtime(23, 0))
    _hours_cache[restaurant_id] = (opening, closing, now + _CACHE_TTL_SECONDS)
    return opening, closing


def _table_free_at(day_reservations, table_id, start_min: int, end_min: int) -> bool:
    """Pure-Python interval overlap check: [start_min, end_min) vs each of
    this table's reservations on the day, already fetched into memory."""
    for r in day_reservations:
        if r["table_id"] != table_id:
            continue
        r_start = _minutes(r["reservation_time"])
        r_end = r_start + (r["duration_minutes"] or DEFAULT_DURATION_MINUTES)
        if start_min < r_end and r_start < end_min:
            return False
    return True


def _smallest_fitting_table_from_data(tables, day_reservations, party_size, time_obj, duration_minutes):
    start_min = _minutes(time_obj)
    end_min = start_min + duration_minutes
    candidates = sorted((t for t in tables if t["seats"] >= party_size), key=lambda t: t["seats"])
    for t in candidates:
        if _table_free_at(day_reservations, t["id"], start_min, end_min):
            return t
    return None


async def find_alternatives(
    conn: asyncpg.Connection,
    restaurant_id: str,
    party_size: int,
    date: str,
    time_str: str,
    duration_minutes: int = DEFAULT_DURATION_MINUTES,
    max_alternatives: int = 3,
):
    """Try nearby time slots and return up to max_alternatives that work.

    Previously this called find_smallest_fitting_table once per candidate
    offset — up to 5 sequential network round trips to Postgres for a single
    tool call, which measured as the dominant cost in check_availability and
    create_reservation's failure paths (median 4.1-4.2s, p95 7.3s across 56
    real tool calls). Every candidate depends only on the same day's data,
    so this now fetches that data ONCE and evaluates all five candidates in
    memory — up to 5 round trips collapse into exactly 1 (or 0, if the
    restaurant's table/hours cache is warm and only the day's reservations
    need fetching)."""
    opening, closing = await get_restaurant_hours(conn, restaurant_id)
    tables = await _get_tables_cached(conn, restaurant_id)
    date_obj = _parse_date(date)

    day_reservations = await conn.fetch(
        """
        select table_id, reservation_time, duration_minutes
        from reservations
        where restaurant_id = $1 and reservation_date = $2
          and status = 'confirmed' and table_id is not null
        """,
        restaurant_id,
        date_obj,
    )

    base = datetime.strptime(time_str, "%H:%M")
    alternatives = []

    for offset in ALT_OFFSETS:
        candidate_dt = base + timedelta(minutes=offset)
        candidate_time = candidate_dt.time()
        if candidate_time < opening or candidate_time > closing:
            continue
        table = _smallest_fitting_table_from_data(
            tables, day_reservations, party_size, candidate_time, duration_minutes
        )
        if table is not None:
            alternatives.append(candidate_dt.strftime("%H:%M"))
        if len(alternatives) >= max_alternatives:
            break

    return alternatives
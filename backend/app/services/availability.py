from datetime import datetime, timedelta, time as dtime, date as ddate
import asyncpg

DEFAULT_DURATION_MINUTES = 90
DEFAULT_RESTAURANT_ID = "11111111-1111-1111-1111-111111111111"

# Offsets (in minutes) tried, in order, when the requested slot doesn't fit.
ALT_OFFSETS = [30, -30, 60, -60, 90]


def _parse_date(date):
    return date if isinstance(date, ddate) else datetime.strptime(date, "%Y-%m-%d").date()


def _parse_time(time_str):
    return time_str if isinstance(time_str, dtime) else datetime.strptime(time_str, "%H:%M").time()


async def find_smallest_fitting_table(
    conn: asyncpg.Connection,
    restaurant_id: str,
    party_size: int,
    date: str,
    time_str: str,
    duration_minutes: int = DEFAULT_DURATION_MINUTES,
):
    """Returns the smallest table (row) that fits party_size and is free
    for the [time_str, time_str+duration) window on `date`, or None."""
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


async def get_restaurant_hours(conn: asyncpg.Connection, restaurant_id: str):
    row = await conn.fetchrow(
        "select opening_time, closing_time from restaurants where id = $1",
        restaurant_id,
    )
    if row is None:
        return dtime(11, 0), dtime(23, 0)
    return row["opening_time"], row["closing_time"]


async def find_alternatives(
    conn: asyncpg.Connection,
    restaurant_id: str,
    party_size: int,
    date: str,
    time_str: str,
    duration_minutes: int = DEFAULT_DURATION_MINUTES,
    max_alternatives: int = 3,
):
    """Try nearby time slots and return up to max_alternatives that work."""
    opening, closing = await get_restaurant_hours(conn, restaurant_id)
    base = datetime.strptime(time_str, "%H:%M")
    alternatives = []

    for offset in ALT_OFFSETS:
        candidate_dt = base + timedelta(minutes=offset)
        candidate_time = candidate_dt.time()
        if candidate_time < opening or candidate_time > closing:
            continue
        candidate_str = candidate_dt.strftime("%H:%M")
        row = await find_smallest_fitting_table(
            conn, restaurant_id, party_size, date, candidate_str, duration_minutes
        )
        if row is not None:
            alternatives.append(candidate_str)
        if len(alternatives) >= max_alternatives:
            break

    return alternatives
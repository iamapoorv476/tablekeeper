import asyncpg
from datetime import datetime

from app.services.availability import (
    find_smallest_fitting_table,
    find_alternatives,
    DEFAULT_DURATION_MINUTES,
    _parse_date,
    _parse_time,
)
from app.services.guests import get_or_create_guest, lookup_guest_by_phone

_MONTH_ABBR = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _format_summary(party_size: int, date: str, time_str: str, table_label: str) -> str:
    dt = datetime.strptime(f"{date} {time_str}", "%Y-%m-%d %H:%M")
    hour_24 = dt.hour
    period = "AM" if hour_24 < 12 else "PM"
    hour_12 = hour_24 % 12
    if hour_12 == 0:
        hour_12 = 12
    pretty_time = f"{hour_12}:{dt.minute:02d} {period}"
    pretty_date = f"{_MONTH_ABBR[dt.month]} {dt.day}"
    return f"{party_size} guests on {pretty_date} at {pretty_time}, table {table_label}"


async def create_reservation(
    conn: asyncpg.Connection,
    restaurant_id: str,
    party_size: int,
    date: str,
    time_str: str,
    guest_name: str,
    caller_number: str | None,
):
    """Re-checks availability at write time (guards against a slot filling
    between the agent's check_availability call and this call) inside a
    single transaction so two simultaneous bookings can't double-book a table."""
    async with conn.transaction():
        table = await find_smallest_fitting_table(
            conn, restaurant_id, party_size, date, time_str
        )
        if table is None:
            alternatives = await find_alternatives(
                conn, restaurant_id, party_size, date, time_str
            )
            return {
                "success": False,
                "error": "That slot is no longer available.",
                "alternatives": [{"time": t} for t in alternatives],
            }

        guest_id = None
        if caller_number:
            guest_id = await get_or_create_guest(conn, restaurant_id, caller_number, guest_name)

        row = await conn.fetchrow(
            """
            insert into reservations
                (restaurant_id, table_id, guest_id, guest_name,  party_size, reservation_date,
                 reservation_time, duration_minutes, status, source)
            values ($1, $2, $3, $4, $5, $6, $7, $8,  'confirmed', 'voice')
            returning id
            """,
            restaurant_id,
            table["id"],
            guest_id,
            guest_name,
            party_size,
            _parse_date(date),
            _parse_time(time_str),
            DEFAULT_DURATION_MINUTES,
        )

        return {
            "success": True,
            "reservation_id": str(row["id"]),
            "table": table["label"],
            "confirmation_summary": _format_summary(party_size, date, time_str, table["label"]),
        }


async def _resolve_reservation_id(
    conn: asyncpg.Connection, restaurant_id: str, reservation_id: str | None, caller_number: str | None
):
    if reservation_id:
        return reservation_id
    if caller_number:
        row = await conn.fetchrow(
            """
            select r.id from reservations r
            join guests g on g.id = r.guest_id
            where g.restaurant_id = $1 and g.phone_number = $2 and r.status = 'confirmed'
            order by r.created_at desc
            limit 1
            """,
            restaurant_id,
            caller_number,
        )
        if row:
            return str(row["id"])
    return None


async def modify_reservation(
    conn: asyncpg.Connection,
    restaurant_id: str,
    reservation_id: str | None,
    caller_number: str | None,
    new_date: str | None,
    new_time: str | None,
    new_party_size: int | None,
):
    async with conn.transaction():
        resolved_id = await _resolve_reservation_id(conn, restaurant_id, reservation_id, caller_number)
        if resolved_id is None:
            return {"success": False, "error": "Could not find an existing reservation for this caller."}

        current = await conn.fetchrow(
            "select party_size, reservation_date, reservation_time, table_id from reservations where id = $1::uuid",
            resolved_id,
        )
        if current is None:
            return {"success": False, "error": "Reservation not found."}

        target_date = new_date or current["reservation_date"].isoformat()
        target_time = new_time or current["reservation_time"].strftime("%H:%M")
        target_party = new_party_size or current["party_size"]

        # Check whether the *current* table already fits the new slot before
        # searching for a fresh one — avoids unnecessarily moving tables.
        table = await find_smallest_fitting_table(
            conn, restaurant_id, target_party, target_date, target_time
        )
        # find_smallest_fitting_table excludes tables with conflicting reservations,
        # but the reservation being modified is itself the "conflict" if time/date
        # didn't change — exclude it explicitly by checking current table first.
        if table is None and current["table_id"] is not None:
            # allow same table if the only overlap is this reservation itself
            same_table_free = await conn.fetchval(
                """
                select not exists (
                  select 1 from reservations r
                  where r.table_id = $1 and r.id != $2::uuid and r.status = 'confirmed'
                    and r.reservation_date = $3
                    and (r.reservation_time, r.reservation_time + (r.duration_minutes || ' minutes')::interval)
                        overlaps ($4::time, $4::time + ('90' || ' minutes')::interval)
                )
                """,
                current["table_id"],
                resolved_id,
                _parse_date(target_date),
                _parse_time(target_time),
            )
            if same_table_free:
                table_row = await conn.fetchrow(
                    "select id, label, seats from tables where id = $1", current["table_id"]
                )
                if table_row["seats"] >= target_party:
                    table = table_row

        if table is None:
            alternatives = await find_alternatives(
                conn, restaurant_id, target_party, target_date, target_time
            )
            return {
                "success": False,
                "error": "That new slot isn't available.",
                "alternatives": [{"time": t} for t in alternatives],
            }

        await conn.execute(
            """
            update reservations
            set reservation_date = $2::date,
                reservation_time = $3::time,
                party_size = $4,
                table_id = $5,
                status = 'confirmed',
                updated_at = now()
            where id = $1::uuid
            """,
            resolved_id,
            _parse_date(target_date),
            _parse_time(target_time),
            target_party,
            table["id"],
        )

        return {
            "success": True,
            "reservation_id": resolved_id,
            "updated_summary": _format_summary(target_party, target_date, target_time, table["label"]),
        }
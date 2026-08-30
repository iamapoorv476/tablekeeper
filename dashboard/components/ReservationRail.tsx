"use client";

import {
  Reservation,
  OPEN_HOUR,
  CLOSE_HOUR,
  HOUR_HEIGHT,
  railOffset,
  formatTime,
} from "@/lib/types";
import NowLine from "./NowLine";

const HOURS = Array.from(
  { length: CLOSE_HOUR - OPEN_HOUR + 1 },
  (_, i) => OPEN_HOUR + i
);

function hourLabel(hour: number): string {
  const h12 = hour % 12 === 0 ? 12 : hour % 12;
  return `${h12} ${hour < 12 ? "am" : "pm"}`;
}

function ReservationRow({
  reservation,
  isArriving,
}: {
  reservation: Reservation;
  isArriving: boolean;
}) {
  const name = reservation.guests?.name ?? "Walk-in";
  const table = reservation.tables?.label ?? "—";

  return (
    <div
      className="absolute left-14 right-0"
      style={{ top: railOffset(reservation.reservation_time) }}
    >
      <div
        className={[
          "flex items-baseline gap-4 border-l-2 py-2 pl-4 pr-3",
          // The 800ms return is what makes an arrival feel like it settles
          // into the book rather than just blinking.
          "transition-[background-color,border-color] duration-[800ms] ease-out",
          isArriving
            ? "animate-slide-in border-l-amber bg-surface-hi"
            : "border-l-rule bg-transparent",
        ].join(" ")}
      >
        <span className="min-w-0 flex-1 truncate text-[15px] font-medium text-content">
          {name}
        </span>

        <span className="shrink-0 font-mono text-xs text-muted">
          {reservation.party_size}
          <span className="text-muted/60"> guests</span>
        </span>

        <span className="w-16 shrink-0 text-right font-mono text-xs text-muted">
          {table}
        </span>

        <span className="w-20 shrink-0 text-right font-mono text-xs tabular-nums text-content/80">
          {formatTime(reservation.reservation_time)}
        </span>

        <span
          className={[
            "w-12 shrink-0 text-right font-mono text-[10px] uppercase tracking-wider",
            reservation.source === "voice" ? "text-amber/80" : "text-muted/60",
          ].join(" ")}
          title={`Booked via ${reservation.source}`}
        >
          {reservation.source}
        </span>
      </div>
    </div>
  );
}

export default function ReservationRail({
  reservations,
  arrivingIds,
  isToday,
  loading,
}: {
  reservations: Reservation[];
  arrivingIds: Set<string>;
  isToday: boolean;
  loading: boolean;
}) {
  const railHeight = (CLOSE_HOUR - OPEN_HOUR) * HOUR_HEIGHT + HOUR_HEIGHT;

  return (
    <div className="relative" style={{ height: railHeight }}>
      {/* Hour markers and their rules */}
      {HOURS.map((hour, i) => (
        <div
          key={hour}
          className="absolute left-0 right-0 flex items-start"
          style={{ top: i * HOUR_HEIGHT }}
        >
          <span className="w-14 shrink-0 pr-2 text-right font-mono text-[11px] leading-none text-muted/50">
            {hourLabel(hour)}
          </span>
          <span className="mt-[5px] h-px flex-1 bg-rule/50" />
        </div>
      ))}

      {/* The spine */}
      <div
        className="absolute left-14 top-0 w-px bg-rule"
        style={{ height: railHeight }}
      />

      <NowLine isToday={isToday} />

      {reservations.map((r) => (
        <ReservationRow
          key={r.id}
          reservation={r}
          isArriving={arrivingIds.has(r.id)}
        />
      ))}

      {!loading && reservations.length === 0 && (
        <div className="absolute left-14 top-8 pl-4">
          <p className="text-sm text-muted">
            No bookings on the sheet yet.
          </p>
          <p className="mt-1 font-mono text-xs text-muted/60">
            Call the number and one will land here mid-sentence.
          </p>
        </div>
      )}
    </div>
  );
}
"use client";

import { Reservation, TableRow, formatTime } from "@/lib/types";

/**
 * Answers exactly one question at a glance: what's open.
 * No floor plan illustration, no drag-and-drop, no capacity maths — those
 * would all be clutter on a screen someone glances at between seatings.
 */
export default function FloorMap({
  tables,
  reservations,
}: {
  tables: TableRow[];
  reservations: Reservation[];
}) {
  const bookingsByTable = new Map<string, Reservation[]>();
  for (const r of reservations) {
    const label = r.tables?.label;
    if (!label) continue;
    const list = bookingsByTable.get(label) ?? [];
    list.push(r);
    bookingsByTable.set(label, list);
  }

  return (
    <div className="grid grid-cols-2 gap-2">
      {tables.map((t) => {
        const booked = bookingsByTable.get(t.label) ?? [];
        const isBooked = booked.length > 0;
        const next = booked[0];

        return (
          <div
            key={t.id}
            className={[
              "rounded-sm border px-3 py-2.5 transition-colors duration-500",
              isBooked
                ? "border-amber-dim bg-surface-hi"
                : "border-rule/60 bg-surface",
            ].join(" ")}
          >
            <div className="flex items-baseline justify-between">
              <span className="font-mono text-sm text-content">{t.label}</span>
              <span className="font-mono text-[10px] text-muted/70">
                {t.seats} seats
              </span>
            </div>

            <div className="mt-1.5 font-mono text-[11px]">
              {isBooked ? (
                <span className="text-amber/90">
                  {formatTime(next.reservation_time)}
                  {booked.length > 1 && (
                    <span className="text-muted/70">
                      {" "}
                      +{booked.length - 1}
                    </span>
                  )}
                </span>
              ) : (
                <span className="text-muted/50">open</span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
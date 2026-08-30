"use client";

import { useEffect, useState } from "react";
import { OPEN_HOUR, CLOSE_HOUR, HOUR_HEIGHT } from "@/lib/types";

/**
 * A 1px amber rule sitting at the current time on the rail.
 *
 * This is deliberately the only "live" indicator in the interface. It proves
 * the page is running the same way a clock does — by moving — and it answers
 * the question a host actually has, which is what's next relative to now.
 * That's why there's no pulsing dot anywhere else.
 */
export default function NowLine({ isToday }: { isToday: boolean }) {
  const [minutes, setMinutes] = useState<number | null>(null);

  useEffect(() => {
    const tick = () => {
      const now = new Date();
      setMinutes(now.getHours() * 60 + now.getMinutes());
    };
    tick();
    const id = setInterval(tick, 30_000);
    return () => clearInterval(id);
  }, []);

  if (!isToday || minutes === null) return null;

  const openMinutes = OPEN_HOUR * 60;
  const closeMinutes = CLOSE_HOUR * 60;
  if (minutes < openMinutes || minutes > closeMinutes) return null;

  const top = ((minutes - openMinutes) / 60) * HOUR_HEIGHT;
  const hour12 = Math.floor(minutes / 60) % 12 || 12;
  const label = `${hour12}:${String(minutes % 60).padStart(2, "0")}`;

  return (
    <div
      className="pointer-events-none absolute left-0 right-0 z-20 flex items-center"
      style={{ top }}
      aria-hidden="true"
    >
      <span className="w-14 shrink-0 pr-2 text-right font-mono text-[10px] text-amber">
        {label}
      </span>
      <span className="h-px flex-1 bg-amber/70" />
    </div>
  );
}
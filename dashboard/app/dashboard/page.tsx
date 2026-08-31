"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { supabase } from "@/lib/supabaseClient";
import {
  Reservation,
  TableRow,
  Callback,
  toDateKey,
  formatDateKey,
} from "@/lib/types";
import ReservationRail from "@/components/ReservationRail";
import FloorMap from "@/components/FloorMap";
import CallbackQueue from "@/components/CallbackQueue";

const SELECT = `
  id, party_size, reservation_date, reservation_time, duration_minutes,
  status, source, created_at, guest_name,
  tables ( label, seats ),
  guests ( name, preferences )
`;

/** How long a newly arrived row stays lit before settling into the record. */
const ARRIVAL_HOLD_MS = 3000;

type ConnectionState = "connecting" | "live" | "error";

export default function DashboardPage() {
  const [dateKey, setDateKey] = useState(() => toDateKey(new Date()));
  const [reservations, setReservations] = useState<Reservation[]>([]);
  const [tables, setTables] = useState<TableRow[]>([]);
  const [callbacks, setCallbacks] = useState<Callback[]>([]);
  const [arrivingIds, setArrivingIds] = useState<Set<string>>(new Set());
  const [connection, setConnection] = useState<ConnectionState>("connecting");
  const [loading, setLoading] = useState(true);

  // The realtime handler is registered once but needs to know which date is
  // on screen right now. A ref avoids tearing down the socket on every change.
  const dateKeyRef = useRef(dateKey);
  useEffect(() => {
    dateKeyRef.current = dateKey;
  }, [dateKey]);

  const todayKey = toDateKey(new Date());
  const isToday = dateKey === todayKey;

  const loadReservations = useCallback(async (key: string) => {
    const { data, error } = await supabase
      .from("reservations")
      .select(SELECT)
      .eq("reservation_date", key)
      .eq("status", "confirmed")
      .order("reservation_time", { ascending: true });

    if (error) {
      console.error("Failed to load reservations:", error.message);
      return;
    }
    setReservations((data ?? []) as unknown as Reservation[]);
  }, []);

  // Callbacks are not date-scoped: an open request stays open until a human
  // clears it, regardless of which service day it came in on.
  const loadCallbacks = useCallback(async () => {
    const { data, error } = await supabase
      .from("callbacks")
      .select("id, caller_number, guest_name, reason, context, status, created_at")
      .eq("status", "open")
      .order("created_at", { ascending: false });
    if (error) {
      console.error("Failed to load callbacks:", error.message);
      return;
    }
    setCallbacks((data ?? []) as Callback[]);
  }, []);

  const resolveCallback = useCallback(
    async (id: string) => {
      // Optimistic: clear it locally, then persist. Realtime will reconcile.
      setCallbacks((prev) => prev.filter((c) => c.id !== id));
      const { error } = await supabase
        .from("callbacks")
        .update({ status: "resolved", resolved_at: new Date().toISOString() })
        .eq("id", id);
      if (error) {
        console.error("Failed to resolve callback:", error.message);
        loadCallbacks();
      }
    },
    [loadCallbacks]
  );

  useEffect(() => {
    loadCallbacks();
  }, [loadCallbacks]);

  // Tables change ~never, so they're fetched once rather than per date.
  useEffect(() => {
    (async () => {
      const { data, error } = await supabase
        .from("tables")
        .select("id, label, seats")
        .order("label", { ascending: true });
      if (error) {
        console.error("Failed to load tables:", error.message);
        return;
      }
      setTables((data ?? []) as TableRow[]);
    })();
  }, []);

  useEffect(() => {
    setLoading(true);
    loadReservations(dateKey).finally(() => setLoading(false));
  }, [dateKey, loadReservations]);

  useEffect(() => {
    const channel = supabase
      .channel("reservations-live")
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "reservations" },
        (payload) => {
          const row = (payload.new ?? payload.old) as
            | { id?: string; reservation_date?: string }
            | undefined;

          // Ignore changes for days that aren't on screen.
          if (row?.reservation_date && row.reservation_date !== dateKeyRef.current) {
            return;
          }

          // The realtime payload carries only the reservations row, not the
          // joined guest name or table label, so refetch the enriched list
          // rather than trying to patch a partial row into state.
          loadReservations(dateKeyRef.current);

          if (payload.eventType === "INSERT" && row?.id) {
            const id = row.id;
            setArrivingIds((prev) => new Set(prev).add(id));
            setTimeout(() => {
              setArrivingIds((prev) => {
                const next = new Set(prev);
                next.delete(id);
                return next;
              });
            }, ARRIVAL_HOLD_MS);
          }
        }
      )
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "callbacks" },
        () => {
          loadCallbacks();
        }
      )
      .subscribe((status) => {
        if (status === "SUBSCRIBED") setConnection("live");
        else if (status === "CHANNEL_ERROR" || status === "TIMED_OUT")
          setConnection("error");
      });

    return () => {
      supabase.removeChannel(channel);
    };
  }, [loadReservations, loadCallbacks]);

  const shiftDay = (delta: number) => {
    const [y, m, d] = dateKey.split("-").map(Number);
    const next = new Date(y, m - 1, d + delta);
    setDateKey(toDateKey(next));
  };

  const covers = reservations.reduce((sum, r) => sum + r.party_size, 0);

  return (
    <main className="min-h-screen bg-ink">
      <header className="border-b border-rule">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
          <div>
            <Link
              href="/"
              className="font-display text-lg text-content hover:text-amber"
            >
              Basilico Trattoria
            </Link>
            <p className="mt-0.5 font-mono text-[11px] uppercase tracking-[0.18em] text-muted/70">
              Service sheet
            </p>
          </div>

          <div className="flex items-center gap-3 font-mono text-[11px]">
            <span
              className={
                connection === "live"
                  ? "text-amber"
                  : connection === "error"
                    ? "text-muted"
                    : "text-muted/60"
              }
            >
              {connection === "live"
                ? "live"
                : connection === "error"
                  ? "reconnecting"
                  : "connecting"}
            </span>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-6xl px-6 py-8">
        <div className="mb-8 flex items-end justify-between border-b border-rule/60 pb-5">
          <div>
            <h1 className="font-display text-3xl text-content">
              {formatDateKey(dateKey)}
            </h1>
            <p className="mt-1.5 font-mono text-xs text-muted">
              {reservations.length}{" "}
              {reservations.length === 1 ? "booking" : "bookings"} · {covers}{" "}
              covers
            </p>
          </div>

          <div className="flex items-center gap-1">
            <button
              onClick={() => shiftDay(-1)}
              className="rounded-sm border border-rule px-2.5 py-1.5 font-mono text-xs text-muted hover:border-muted hover:text-content"
              aria-label="Previous day"
            >
              ←
            </button>
            {!isToday && (
              <button
                onClick={() => setDateKey(todayKey)}
                className="rounded-sm border border-rule px-3 py-1.5 font-mono text-xs text-muted hover:border-muted hover:text-content"
              >
                today
              </button>
            )}
            <button
              onClick={() => shiftDay(1)}
              className="rounded-sm border border-rule px-2.5 py-1.5 font-mono text-xs text-muted hover:border-muted hover:text-content"
              aria-label="Next day"
            >
              →
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-10 lg:grid-cols-[1fr_260px]">
          <section aria-label="Reservations by time">
            <ReservationRail
              reservations={reservations}
              arrivingIds={arrivingIds}
              isToday={isToday}
              loading={loading}
            />
          </section>

          <aside className="lg:sticky lg:top-8 lg:self-start">
            <h2 className="mb-3 flex items-baseline gap-2 font-mono text-[11px] uppercase tracking-[0.18em] text-muted/70">
              Needs a callback
              {callbacks.length > 0 && (
                <span className="text-amber">{callbacks.length}</span>
              )}
            </h2>
            <CallbackQueue callbacks={callbacks} onResolve={resolveCallback} />

            <h2 className="mb-3 mt-8 font-mono text-[11px] uppercase tracking-[0.18em] text-muted/70">
              Floor
            </h2>
            <FloorMap tables={tables} reservations={reservations} />

            <p className="mt-4 font-mono text-[10px] leading-relaxed text-muted/50">
              Tables fill as the agent books them. Nothing here polls — rows
              arrive over a Postgres change stream.
            </p>
          </aside>
        </div>
      </div>
    </main>
  );
}
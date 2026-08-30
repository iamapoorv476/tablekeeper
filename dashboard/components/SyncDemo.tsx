"use client";

import { useEffect, useState } from "react";

/**
 * The thesis of the whole project, as a loop: a call on the left, the floor's
 * screen on the right, one booking crossing between them. The transcript is
 * lifted from a real call against the deployed agent.
 */

type Line =
  | { kind: "agent" | "caller"; text: string }
  | { kind: "tool"; text: string };

const SCRIPT: Line[] = [
  { kind: "agent", text: "Thanks for calling Basilico Trattoria, this is Mia — how can I help you today?" },
  { kind: "caller", text: "Hi, table for four tonight at 7:30?" },
  { kind: "tool", text: "check_availability · party 4 · 19:30" },
  { kind: "agent", text: "We've got a four-top at 7:30. What name should I put it under?" },
  { kind: "caller", text: "Aarav." },
  { kind: "tool", text: "create_reservation · T3" },
  { kind: "agent", text: "You're all set — 4 guests tonight at 7:30 PM, table T3." },
];

/** The step at which the booking lands on the rail. */
const COMMIT_STEP = 5;

const EXISTING = [
  { time: "6:00", name: "Priya Nair", size: 2, table: "T1" },
  { time: "6:45", name: "The Osmans", size: 6, table: "T5" },
];

export default function SyncDemo() {
  const [step, setStep] = useState(-1);

  useEffect(() => {
    let timeout: ReturnType<typeof setTimeout>;

    const advance = (i: number) => {
      setStep(i);
      const isLast = i >= SCRIPT.length - 1;
      const delay = isLast ? 4200 : SCRIPT[i]?.kind === "tool" ? 900 : 2100;
      timeout = setTimeout(() => advance(isLast ? -1 : i + 1), delay);
    };

    timeout = setTimeout(() => advance(0), 700);
    return () => clearTimeout(timeout);
  }, []);

  const committed = step >= COMMIT_STEP;
  const justCommitted = step === COMMIT_STEP || step === COMMIT_STEP + 1;
  const visible = SCRIPT.slice(0, Math.max(step + 1, 0));

  return (
    <div className="grid grid-cols-1 overflow-hidden rounded-sm border border-rule md:grid-cols-2">
      {/* Left: the call */}
      <div className="border-b border-rule bg-surface/50 p-5 md:border-b-0 md:border-r">
        <div className="mb-4 flex items-center justify-between">
          <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted/70">
            Inbound call
          </span>
          <span className="flex items-center gap-1.5 font-mono text-[10px] text-amber">
            <span className="inline-block h-1 w-1 rounded-full bg-amber" />
            connected
          </span>
        </div>

        <div className="flex min-h-[280px] flex-col gap-2.5">
          {visible.map((line, i) => {
            if (line.kind === "tool") {
              return (
                <div
                  key={i}
                  className="my-0.5 flex items-center gap-2 font-mono text-[10px] text-amber/80"
                >
                  <span className="h-px w-3 bg-amber/40" />
                  {line.text}
                </div>
              );
            }
            const isAgent = line.kind === "agent";
            return (
              <div
                key={i}
                className={isAgent ? "pr-6" : "self-end pl-6 text-right"}
              >
                <span className="mb-0.5 block font-mono text-[10px] uppercase tracking-wider text-muted/50">
                  {isAgent ? "Mia" : "Caller"}
                </span>
                <span
                  className={[
                    "inline-block rounded-sm px-2.5 py-1.5 text-[13px] leading-snug",
                    isAgent
                      ? "bg-surface-hi text-content/90"
                      : "bg-surface text-muted",
                  ].join(" ")}
                >
                  {line.text}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Right: the floor's screen */}
      <div className="bg-ink p-5">
        <div className="mb-4 flex items-center justify-between">
          <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted/70">
            Service sheet
          </span>
          <span className="font-mono text-[10px] text-amber">live</span>
        </div>

        <div className="min-h-[280px] space-y-px">
          {EXISTING.map((r) => (
            <Row key={r.time} {...r} />
          ))}

          <div
            className={[
              "transition-opacity duration-300",
              committed ? "opacity-100" : "pointer-events-none opacity-0",
            ].join(" ")}
          >
            {committed && (
              <Row
                time="7:30"
                name="Aarav"
                size={4}
                table="T3"
                arriving={justCommitted}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function Row({
  time,
  name,
  size,
  table,
  arriving = false,
}: {
  time: string;
  name: string;
  size: number;
  table: string;
  arriving?: boolean;
}) {
  return (
    <div
      className={[
        "flex items-baseline gap-3 border-l-2 py-2 pl-3 pr-2",
        "transition-[background-color,border-color] duration-[800ms] ease-out",
        arriving
          ? "animate-slide-in border-l-amber bg-surface-hi"
          : "border-l-rule bg-transparent",
      ].join(" ")}
    >
      <span className="w-12 shrink-0 font-mono text-[11px] tabular-nums text-muted/70">
        {time}
      </span>
      <span className="min-w-0 flex-1 truncate text-[13px] text-content">
        {name}
      </span>
      <span className="shrink-0 font-mono text-[11px] text-muted">{size}</span>
      <span className="w-8 shrink-0 text-right font-mono text-[11px] text-muted">
        {table}
      </span>
    </div>
  );
}
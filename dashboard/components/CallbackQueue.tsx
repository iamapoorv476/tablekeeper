"use client";

import { Callback } from "@/lib/types";

/**
 * What the agent couldn't close on the call.
 *
 * This is the counterpart to the rail: the rail is what went right, this is
 * what needs a human. Resolving from here writes back to Postgres, which makes
 * the dashboard a second writing surface onto the same brain rather than a
 * read-only viewer.
 */
export default function CallbackQueue({
  callbacks,
  onResolve,
}: {
  callbacks: Callback[];
  onResolve: (id: string) => void;
}) {
  if (callbacks.length === 0) {
    return (
      <p className="font-mono text-[11px] text-muted/50">
        Nothing waiting on a human.
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {callbacks.map((c) => (
        <div
          key={c.id}
          className="border-l-2 border-l-amber bg-surface-hi/60 py-2.5 pl-3 pr-2.5"
        >
          <div className="flex items-baseline justify-between gap-2">
            <span className="text-[13px] font-medium text-content">
              {c.guest_name ?? "Unknown caller"}
            </span>
            <button
              onClick={() => onResolve(c.id)}
              className="shrink-0 font-mono text-[10px] text-muted transition-colors hover:text-amber"
            >
              done
            </button>
          </div>

          {c.caller_number && (
            <p className="mt-0.5 font-mono text-[10px] text-amber/80">
              {c.caller_number}
            </p>
          )}

          <p className="mt-1.5 text-[12px] leading-snug text-content/80">
            {c.context}
          </p>

          <p className="mt-1 font-mono text-[10px] leading-snug text-muted/60">
            {c.reason}
          </p>
        </div>
      ))}
    </div>
  );
}
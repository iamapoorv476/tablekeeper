import Link from "next/link";
import SyncDemo from "@/components/SyncDemo";

const STEPS = [
  {
    n: "01",
    title: "The phone rings",
    body: "A voice agent picks up as the restaurant. It recognises returning numbers and greets them by name.",
  },
  {
    n: "02",
    title: "It checks the floor",
    body: "Before it promises anything, the agent queries real table capacity for that slot and offers alternatives when nothing fits.",
  },
  {
    n: "03",
    title: "It writes to Postgres",
    body: "The booking is committed inside a transaction that re-checks availability, so two callers can't take the same table.",
  },
  {
    n: "04",
    title: "The floor sees it",
    body: "The change streams to the service sheet over Postgres replication. The row lands while the caller is still on the line.",
  },
];

const PAINS = [
  {
    title: "Calls go unanswered",
    body: "The phone rings hardest at 7pm, which is exactly when nobody can stop to answer it. Those covers don't come back.",
  },
  {
    title: "The same table, twice",
    body: "A booking taken on the phone and one taken by email don't know about each other until two parties are standing at the door.",
  },
  {
    title: "No single view of the night",
    body: "The book, the inbox, and the widget each hold part of the truth, and the host reconciles them from memory.",
  },
];

export default function Home() {
  return (
    <main className="min-h-screen bg-ink">
      <header className="border-b border-rule">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-5">
          <span className="font-display text-lg">Basilico Trattoria</span>
          <Link
            href="/dashboard"
            className="font-mono text-xs text-muted transition-colors hover:text-amber"
          >
            open the service sheet →
          </Link>
        </div>
      </header>

      {/* Hero — the thesis is the demo, not the headline */}
      <section className="mx-auto max-w-5xl px-6 pb-20 pt-16 md:pt-24">
        <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-amber/80">
          Voice agent · shared state
        </p>
        <h1 className="mt-5 max-w-2xl font-display text-5xl leading-[1.05] text-content md:text-6xl">
          One brain,
          <br />
          two surfaces.
        </h1>
        <p className="mt-6 max-w-xl text-[15px] leading-relaxed text-muted">
          An AI agent answers the restaurant&apos;s phone and books tables. The floor
          watches those bookings land on screen while the call is still
          happening, because both are reading the same database.
        </p>

        <div className="mt-12">
          <SyncDemo />
        </div>
      </section>

      {/* How it works — numbered because it genuinely is a sequence */}
      <section className="border-t border-rule">
        <div className="mx-auto max-w-5xl px-6 py-20">
          <h2 className="font-display text-2xl text-content">
            What happens during the call
          </h2>

          <div className="mt-10 grid grid-cols-1 gap-px border-t border-rule/60 sm:grid-cols-2 lg:grid-cols-4">
            {STEPS.map((s) => (
              <div key={s.n} className="border-t border-rule/60 pr-4 pt-5 lg:border-t-0">
                <span className="font-mono text-[11px] text-amber/70">{s.n}</span>
                <h3 className="mt-2.5 text-[15px] font-medium text-content">
                  {s.title}
                </h3>
                <p className="mt-2 text-[13px] leading-relaxed text-muted">
                  {s.body}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Demo video */}
      <section className="border-t border-rule">
        <div className="mx-auto max-w-5xl px-6 py-20">
          <h2 className="font-display text-2xl text-content">
            Sixty seconds, one call
          </h2>
          <p className="mt-3 max-w-lg text-[15px] leading-relaxed text-muted">
            A real call to a real number, booking a real table, with the service
            sheet open beside it.
          </p>

          <div className="mt-8 aspect-video w-full border border-rule bg-surface/40">
            {/* Drop the recording in /public and swap this for a <video> tag. */}
            <div className="flex h-full items-center justify-center">
              <span className="font-mono text-xs text-muted/50">
                demo.mp4
              </span>
            </div>
          </div>

          <p className="mt-4 font-mono text-[11px] text-muted/60">
            median tool round-trip — measured across the agent&apos;s live calls
          </p>
        </div>
      </section>

      {/* Why it matters */}
      <section className="border-t border-rule">
        <div className="mx-auto max-w-5xl px-6 py-20">
          <h2 className="font-display text-2xl text-content">
            Why a shared brain, and not four bots
          </h2>

          <div className="mt-10 grid grid-cols-1 gap-8 md:grid-cols-3">
            {PAINS.map((p) => (
              <div key={p.title}>
                <h3 className="text-[15px] font-medium text-content">
                  {p.title}
                </h3>
                <p className="mt-2 text-[13px] leading-relaxed text-muted">
                  {p.body}
                </p>
              </div>
            ))}
          </div>

          <p className="mt-10 max-w-xl text-[13px] leading-relaxed text-muted/80">
            Each of those is the same failure: a booking surface that doesn&apos;t
            know what the others have promised. Fixing it isn&apos;t a matter of
            adding agents. It&apos;s a matter of pointing them all at one source of
            truth.
          </p>
        </div>
      </section>

      <footer className="border-t border-rule">
        <div className="mx-auto flex max-w-5xl flex-col gap-4 px-6 py-10 sm:flex-row sm:items-center sm:justify-between">
          <p className="font-mono text-[11px] text-muted/60">
            Next.js · FastAPI · Supabase · Vapi · Claude Haiku
          </p>
          <Link
            href="/dashboard"
            className="font-mono text-[11px] text-muted transition-colors hover:text-amber"
          >
            open the service sheet →
          </Link>
        </div>
      </footer>
    </main>
  );
}
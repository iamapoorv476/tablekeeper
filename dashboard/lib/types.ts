export type Reservation = {
  id: string;
  party_size: number;
  reservation_date: string; // YYYY-MM-DD
  reservation_time: string; // HH:MM:SS
  duration_minutes: number | null;
  status: string;
  source: string;
  created_at: string;
  tables: { label: string; seats: number } | null;
  guests: { name: string | null; preferences: string | null } | null;
};

export type TableRow = {
  id: string;
  label: string;
  seats: number;
};

/** Service window shown on the rail. Matches the seeded restaurant hours. */
export const OPEN_HOUR = 11;
export const CLOSE_HOUR = 23;
export const HOUR_HEIGHT = 64; // px per hour on the rail

/** "HH:MM:SS" -> minutes since midnight. Tolerates "HH:MM" too. */
export function timeToMinutes(time: string): number {
  const [h, m] = time.split(":").map(Number);
  return h * 60 + (m || 0);
}

/** Vertical offset in px for a given time, relative to the top of the rail. */
export function railOffset(time: string): number {
  const minutes = timeToMinutes(time) - OPEN_HOUR * 60;
  return (minutes / 60) * HOUR_HEIGHT;
}

/** 19:30:00 -> "7:30 PM". Built by hand rather than toLocaleTimeString so the
 *  server and client render identically and React doesn't flag a hydration
 *  mismatch from differing locales/timezones. */
export function formatTime(time: string): string {
  const [h, m] = time.split(":").map(Number);
  const period = h < 12 ? "AM" : "PM";
  const hour12 = h % 12 === 0 ? 12 : h % 12;
  return `${hour12}:${String(m || 0).padStart(2, "0")} ${period}`;
}

/** Local YYYY-MM-DD. Avoids toISOString(), which converts to UTC and can
 *  land on the wrong calendar day for anyone east or west of Greenwich. */
export function toDateKey(d: Date): string {
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];
const DAYS = [
  "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday",
];

export function formatDateKey(key: string): string {
  const [y, m, d] = key.split("-").map(Number);
  const date = new Date(y, m - 1, d);
  return `${DAYS[date.getDay()]}, ${MONTHS[m - 1]} ${d}`;
}
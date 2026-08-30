import { createClient } from "@supabase/supabase-js";

const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

if (!url || !anonKey) {
  throw new Error(
    "Missing NEXT_PUBLIC_SUPABASE_URL or NEXT_PUBLIC_SUPABASE_ANON_KEY. " +
      "Copy .env.local.example to .env.local and fill both in."
  );
}

export const supabase = createClient(url, anonKey, {
  realtime: {
    params: {
      // Cap how fast the socket will replay changes. The dashboard is a
      // human-paced surface; 10/sec is far more than a dining room produces.
      eventsPerSecond: 10,
    },
  },
});
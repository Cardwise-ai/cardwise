// NEXT_PUBLIC_ values are inlined at build time, so each one is read by its literal name.

/** Mock mode swaps the API and Supabase for MSW and a cookie session. Never set it on Vercel. */
export const isMocking = process.env.NEXT_PUBLIC_API_MOCKING === "enabled";

export const apiUrl = (process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(
  /\/+$/,
  "",
);

export function supabaseConfig(): { url: string; anonKey: string } {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !anonKey) {
    throw new Error(
      "NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY must be set. See docs/external-services.md.",
    );
  }
  return { url, anonKey };
}

export const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;

/**
 * "free" while answers come from free model tiers, which shows the free-tier notice. The API has
 * no public config endpoint, so the web build carries the setting. Anything but "paid" is free.
 */
export const llmTier: "free" | "paid" =
  process.env.NEXT_PUBLIC_LLM_TIER === "paid" ? "paid" : "free";

/** The API's per-user hourly message limit (spec 7.2). */
export const MESSAGES_PER_HOUR = 20;

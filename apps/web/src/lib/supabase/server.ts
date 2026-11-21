import "server-only";

import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";
import { supabaseConfig } from "@/lib/env";

/** A fresh client per request. Cookie writes from Server Components are ignored; the proxy refreshes. */
export async function createSupabaseServerClient() {
  // Reading cookies first keeps prerendering from reaching the env check at build time.
  const cookieStore = await cookies();
  const { url, anonKey } = supabaseConfig();
  return createServerClient(url, anonKey, {
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      setAll(cookiesToSet) {
        try {
          for (const { name, value, options } of cookiesToSet) {
            cookieStore.set(name, value, options);
          }
        } catch {
          // Called from a Server Component, where cookies are read-only.
        }
      },
    },
  });
}

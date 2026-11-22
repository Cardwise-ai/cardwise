"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { MOCK_SESSION_COOKIE, safeNextPath } from "@/lib/auth/shared";
import { isMocking } from "@/lib/env";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export async function signOut(): Promise<void> {
  if (isMocking) {
    (await cookies()).delete(MOCK_SESSION_COOKIE);
  } else {
    const supabase = await createSupabaseServerClient();
    await supabase.auth.signOut();
  }
  redirect("/sign-in");
}

/**
 * Clears a session the API no longer accepts and returns the sign-in URL to load. Without this,
 * the proxy would still see the cookie as signed in and bounce the reader away from sign-in.
 */
export async function endRejectedSession(next: unknown): Promise<string> {
  const store = await cookies();
  if (isMocking) {
    store.delete(MOCK_SESSION_COOKIE);
  } else {
    const supabase = await createSupabaseServerClient();
    // "local" ends only this browser's session; other devices stay signed in.
    await supabase.auth.signOut({ scope: "local" }).catch(() => undefined);
    for (const cookie of store.getAll()) {
      if (cookie.name.startsWith("sb-")) store.delete(cookie.name);
    }
  }
  const params = new URLSearchParams({ error: "session" });
  const path = safeNextPath(next);
  if (path !== "/") params.set("next", path);
  return `/sign-in?${params.toString()}`;
}

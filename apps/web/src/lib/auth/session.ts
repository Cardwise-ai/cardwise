import "server-only";

import { cookies } from "next/headers";
import { isMocking } from "@/lib/env";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { MOCK_SESSION_COOKIE, type SessionUser } from "./shared";

/** The signed-in user for this request, verified against Supabase, or null. */
export async function getCurrentUser(): Promise<SessionUser | null> {
  if (isMocking) {
    const value = (await cookies()).get(MOCK_SESSION_COOKIE)?.value;
    return value ? { email: value } : null;
  }
  const supabase = await createSupabaseServerClient();
  const { data, error } = await supabase.auth.getClaims();
  if (error || !data) return null;
  const email = data.claims.email;
  return { email: typeof email === "string" ? email : "" };
}

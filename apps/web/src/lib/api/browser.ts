"use client";

import { MOCK_ACCESS_TOKEN } from "@/lib/auth/shared";
import { endRejectedSession } from "@/lib/auth/sign-out";
import { apiUrl, isMocking } from "@/lib/env";
import { getSupabaseBrowserClient } from "@/lib/supabase/browser";
import { type ApiClient, createApiClient } from "./client";

/** The Supabase access token for the API's bearer header. Refreshes it when it has expired. */
export async function getAccessToken(): Promise<string | null> {
  if (isMocking) {
    // Every API call passes through here, so this is where mock mode waits for MSW.
    const { startMockWorker } = await import("@/mocks/start");
    await startMockWorker();
    return MOCK_ACCESS_TOKEN;
  }
  const { data } = await getSupabaseBrowserClient().auth.getSession();
  return data.session?.access_token ?? null;
}

/** Asks Supabase for a new access token after the API refused the current one. */
async function refreshAccessToken(): Promise<string | null> {
  if (isMocking) return null;
  const { data, error } = await getSupabaseBrowserClient().auth.refreshSession();
  return error ? null : (data.session?.access_token ?? null);
}

let endingSession = false;

/** The API refused the session even after a refresh: clear it and go to sign-in. */
function onUnauthorized(): void {
  if (endingSession) return;
  endingSession = true;
  const here = `${window.location.pathname}${window.location.search}`;
  // A full page load, not a client navigation, so no state from the ended session survives.
  const go = (url: string) => window.location.assign(url);
  endRejectedSession(here).then(go, () => go("/sign-in?error=session"));
}

let client: ApiClient | undefined;

export function getApiClient(): ApiClient {
  client ??= createApiClient({
    baseUrl: apiUrl,
    getAccessToken,
    refreshAccessToken,
    onUnauthorized,
  });
  return client;
}

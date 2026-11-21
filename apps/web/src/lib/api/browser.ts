"use client";

import { MOCK_ACCESS_TOKEN } from "@/lib/auth/shared";
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

let client: ApiClient | undefined;

export function getApiClient(): ApiClient {
  client ??= createApiClient({ baseUrl: apiUrl, getAccessToken });
  return client;
}

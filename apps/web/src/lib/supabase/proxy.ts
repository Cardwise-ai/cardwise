import { createServerClient } from "@supabase/ssr";
import { type NextRequest, NextResponse } from "next/server";
import { MOCK_SESSION_COOKIE } from "@/lib/auth/shared";
import { isMocking, supabaseConfig } from "@/lib/env";

export interface SessionResult {
  response: NextResponse;
  signedIn: boolean;
}

/**
 * Refreshes the Supabase session and forwards the refreshed cookies both to the page render
 * (request headers) and to the browser (response). Follows the @supabase/ssr Next.js guide.
 */
export async function updateSession(
  request: NextRequest,
  requestHeaders: Headers,
): Promise<SessionResult> {
  if (isMocking) {
    return {
      response: NextResponse.next({ request: { headers: requestHeaders } }),
      signedIn: Boolean(request.cookies.get(MOCK_SESSION_COOKIE)?.value),
    };
  }

  const { url, anonKey } = supabaseConfig();
  let response = NextResponse.next({ request: { headers: requestHeaders } });

  const supabase = createServerClient(url, anonKey, {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(cookiesToSet, headers) {
        for (const { name, value } of cookiesToSet) request.cookies.set(name, value);
        const cookieHeader = request.headers.get("cookie");
        if (cookieHeader) requestHeaders.set("cookie", cookieHeader);
        response = NextResponse.next({ request: { headers: requestHeaders } });
        for (const { name, value, options } of cookiesToSet) {
          response.cookies.set(name, value, options);
        }
        for (const [key, value] of Object.entries(headers)) response.headers.set(key, value);
      },
    },
  });

  // getClaims() validates the JWT; never trust getSession() on the server.
  const { data, error } = await supabase.auth.getClaims();
  return { response, signedIn: !error && Boolean(data?.claims.sub) };
}

/** A redirect that keeps any refreshed auth cookies from `from`. */
export function redirectWithCookies(url: URL, from: NextResponse): NextResponse {
  const redirect = NextResponse.redirect(url);
  for (const cookie of from.cookies.getAll()) redirect.cookies.set(cookie);
  const cacheControl = from.headers.get("cache-control");
  if (cacheControl) redirect.headers.set("cache-control", cacheControl);
  return redirect;
}

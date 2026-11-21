import { type NextRequest } from "next/server";
import { isPublicPath } from "@/lib/auth/shared";
import { apiUrl, isMocking, supabaseUrl } from "@/lib/env";
import { buildCsp, createNonce, cspHeaderName, CSP_REPORT_PATH } from "@/lib/security/csp";
import { redirectWithCookies, updateSession } from "@/lib/supabase/proxy";

export async function proxy(request: NextRequest) {
  const nonce = createNonce();
  const csp = buildCsp({
    nonce,
    isDev: process.env.NODE_ENV === "development",
    apiUrl,
    supabaseUrl,
    allowServiceWorker: isMocking,
  });

  // Next.js reads the nonce from this request header and stamps it on its own scripts.
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set(cspHeaderName, csp);

  const { response, signedIn } = await updateSession(request, requestHeaders);
  const { pathname, search } = request.nextUrl;

  let result = response;
  if (!signedIn && !isPublicPath(pathname)) {
    const url = new URL("/sign-in", request.url);
    if (pathname !== "/") url.searchParams.set("next", pathname + search);
    result = redirectWithCookies(url, response);
  } else if (signedIn && pathname === "/sign-in") {
    result = redirectWithCookies(new URL("/", request.url), response);
  }

  result.headers.set(cspHeaderName, csp);
  result.headers.set("Reporting-Endpoints", `csp="${CSP_REPORT_PATH}"`);
  return result;
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|mockServiceWorker.js|csp-report|.*\\.(?:svg|png|jpg|jpeg|gif|webp|woff2)$).*)",
  ],
};

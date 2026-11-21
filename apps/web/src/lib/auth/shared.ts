/** Mock mode only: the cookie that stands in for a Supabase session. */
export const MOCK_SESSION_COOKIE = "cw_mock_session";
export const MOCK_ACCESS_TOKEN = "mock-access-token";

export interface SessionUser {
  email: string;
}

/** Routes anyone can open. Everything else needs a session. */
export function isPublicPath(pathname: string): boolean {
  return (
    pathname === "/sign-in" ||
    pathname.startsWith("/auth/") ||
    pathname === "/tokens" ||
    pathname === "/csp-report"
  );
}

/** Only same-site paths are allowed as post-sign-in destinations. */
export function safeNextPath(value: unknown): string {
  if (typeof value !== "string" || !value.startsWith("/") || value.startsWith("//")) return "/";
  if (value.startsWith("/\\") || value.includes("\n") || value.includes("\r")) return "/";
  return value;
}

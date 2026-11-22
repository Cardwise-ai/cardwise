/** Parses an http(s) origin. Plain http is accepted only for local development hosts. */
function parseOrigin(value: string | null | undefined): string | null {
  if (!value) return null;
  let url: URL;
  try {
    url = new URL(value.includes("://") ? value : `https://${value}`);
  } catch {
    return null;
  }
  if (url.username || url.password) return null;
  const local = url.hostname === "localhost" || url.hostname === "127.0.0.1";
  if (url.protocol !== "https:" && !(url.protocol === "http:" && local)) return null;
  return url.origin;
}

/**
 * The origin Supabase should send users back to after Google or email sign-in. Supabase silently
 * replaces a redirect it does not allow with its Site URL, so a stable, allowlisted origin wins
 * over whatever host the visitor happens to be on:
 *
 * 1. NEXT_PUBLIC_SITE_URL, when set (the canonical web URL for an environment);
 * 2. on Vercel Previews, the branch URL (a system variable), so per-deployment URLs fold into one
 *    allowlisted host. Production never uses it: there it would be the git-main alias, not the
 *    domain users visit;
 * 3. the request's Origin header (local development, or Production without NEXT_PUBLIC_SITE_URL).
 */
export function authOrigin(requestOrigin: string | null): string | null {
  const branchHost =
    process.env.VERCEL_ENV === "preview" ? process.env.VERCEL_BRANCH_URL : undefined;
  return (
    parseOrigin(process.env.NEXT_PUBLIC_SITE_URL) ??
    parseOrigin(branchHost) ??
    parseOrigin(requestOrigin)
  );
}

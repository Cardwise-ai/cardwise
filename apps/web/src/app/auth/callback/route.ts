import { type NextRequest, NextResponse } from "next/server";
import { safeNextPath } from "@/lib/auth/shared";
import { isMocking } from "@/lib/env";
import { createSupabaseServerClient } from "@/lib/supabase/server";

/** Magic-link landing: exchanges the PKCE code for a session cookie, then continues to `next`. */
export async function GET(request: NextRequest) {
  const { searchParams } = request.nextUrl;
  const next = safeNextPath(searchParams.get("next"));
  const code = searchParams.get("code");
  const failed = new URL("/sign-in?error=link", request.url);

  if (isMocking || !code) return NextResponse.redirect(failed);

  const supabase = await createSupabaseServerClient();
  const { error } = await supabase.auth.exchangeCodeForSession(code);
  if (error) return NextResponse.redirect(failed);
  return NextResponse.redirect(new URL(next, request.url));
}

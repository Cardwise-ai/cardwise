import { type NextRequest, NextResponse } from "next/server";
import { safeNextPath } from "@/lib/auth/shared";
import { isMocking } from "@/lib/env";
import { createSupabaseServerClient } from "@/lib/supabase/server";

/** OAuth and magic-link landing: exchanges the PKCE code, then continues to the safe `next` path. */
export async function GET(request: NextRequest) {
  const { searchParams } = request.nextUrl;
  const next = safeNextPath(searchParams.get("next"));
  const code = searchParams.get("code");
  const failureCode = searchParams.get("flow") === "google" ? "google" : "link";
  const failed = new URL(`/sign-in?error=${failureCode}`, request.url);

  if (isMocking || !code) return NextResponse.redirect(failed);

  const supabase = await createSupabaseServerClient();
  const { error } = await supabase.auth.exchangeCodeForSession(code);
  if (error) return NextResponse.redirect(failed);
  return NextResponse.redirect(new URL(next, request.url));
}

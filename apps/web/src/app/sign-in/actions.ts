"use server";

import { cookies, headers } from "next/headers";
import { redirect } from "next/navigation";
import { MOCK_SESSION_COOKIE, safeNextPath } from "@/lib/auth/shared";
import { isMocking } from "@/lib/env";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export interface SignInState {
  status: "idle" | "error" | "sent";
  message?: string;
  email?: string;
}

const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function readEmail(formData: FormData): string {
  const value = formData.get("email");
  return typeof value === "string" ? value.trim() : "";
}

async function startMockSession(email: string) {
  (await cookies()).set(MOCK_SESSION_COOKIE, email, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 60 * 60 * 8,
  });
}

export async function signInWithPassword(
  _previous: SignInState,
  formData: FormData,
): Promise<SignInState> {
  const email = readEmail(formData);
  const password = formData.get("password");
  const next = safeNextPath(formData.get("next"));
  if (!emailPattern.test(email))
    return { status: "error", message: "Enter a valid email address.", email };
  if (typeof password !== "string" || !password) {
    return {
      status: "error",
      message: "Enter your password, or use a sign-in link instead.",
      email,
    };
  }

  if (isMocking) {
    await startMockSession(email);
    redirect(next);
  }

  const supabase = await createSupabaseServerClient();
  const { error } = await supabase.auth.signInWithPassword({ email, password });
  if (error) {
    // Supabase returns the same error for an unknown email and a wrong password; keep it that way.
    return { status: "error", message: "That email and password don't match an account.", email };
  }
  redirect(next);
}

export async function signInWithGoogle(
  _previous: SignInState,
  formData: FormData,
): Promise<SignInState> {
  const email = readEmail(formData);
  const next = safeNextPath(formData.get("next"));

  if (isMocking) {
    await startMockSession("google-reader@example.com");
    redirect(next);
  }

  const origin = (await headers()).get("origin");
  if (!origin)
    return {
      status: "error",
      message: "Something went wrong. Reload the page and try again.",
      email,
    };

  const callback = new URL("/auth/callback", origin);
  callback.searchParams.set("next", next);
  callback.searchParams.set("flow", "google");

  const supabase = await createSupabaseServerClient();
  const { data, error } = await supabase.auth.signInWithOAuth({
    provider: "google",
    options: { redirectTo: callback.toString() },
  });
  if (error || !data.url)
    return {
      status: "error",
      message: "We couldn't start Google sign-in. Try again in a minute.",
      email,
    };

  redirect(data.url);
}

export async function sendMagicLink(
  _previous: SignInState,
  formData: FormData,
): Promise<SignInState> {
  const email = readEmail(formData);
  const next = safeNextPath(formData.get("next"));
  if (!emailPattern.test(email))
    return { status: "error", message: "Enter a valid email address.", email };

  if (isMocking) {
    await startMockSession(email);
    redirect(next);
  }

  const origin = (await headers()).get("origin");
  if (!origin)
    return {
      status: "error",
      message: "Something went wrong. Reload the page and try again.",
      email,
    };
  const callback = new URL("/auth/callback", origin);
  callback.searchParams.set("next", next);

  const supabase = await createSupabaseServerClient();
  const { error } = await supabase.auth.signInWithOtp({
    email,
    options: { emailRedirectTo: callback.toString() },
  });
  if (error?.status === 429) {
    return {
      status: "error",
      message: "Too many sign-in emails. Wait a minute and try again.",
      email,
    };
  }
  if (error)
    return {
      status: "error",
      message: "We couldn't send the email. Try again in a minute.",
      email,
    };
  return { status: "sent", email };
}

import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  createSupabaseServerClient: vi.fn(),
  headers: vi.fn(),
  redirect: vi.fn(),
}));

vi.mock("@/lib/env", () => ({ isMocking: false }));
vi.mock("@/lib/supabase/server", () => ({
  createSupabaseServerClient: mocks.createSupabaseServerClient,
}));
vi.mock("next/headers", () => ({ headers: mocks.headers }));
vi.mock("next/navigation", () => ({ redirect: mocks.redirect }));

import { signInWithGoogle } from "./actions";

const form = (next: string) => {
  const data = new FormData();
  data.set("next", next);
  return data;
};

describe("signInWithGoogle", () => {
  const signInWithOAuth = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    mocks.headers.mockResolvedValue(new Headers({ origin: "https://preview.cardwise.app" }));
    mocks.createSupabaseServerClient.mockResolvedValue({
      auth: { signInWithOAuth },
    });
    mocks.redirect.mockImplementation((url: string) => {
      throw new Error(`redirect:${url}`);
    });
  });

  it("starts Google OAuth with a safe callback and redirects to the provider", async () => {
    const providerUrl = "https://accounts.google.com/o/oauth2/v2/auth?client_id=test";
    signInWithOAuth.mockResolvedValue({ data: { url: providerUrl }, error: null });

    await expect(signInWithGoogle({ status: "idle" }, form("/chats/example"))).rejects.toThrow(
      `redirect:${providerUrl}`,
    );
    expect(signInWithOAuth).toHaveBeenCalledWith({
      provider: "google",
      options: {
        redirectTo:
          "https://preview.cardwise.app/auth/callback?next=%2Fchats%2Fexample&flow=google",
      },
    });
  });

  it("rejects unsafe post-sign-in destinations", async () => {
    signInWithOAuth.mockResolvedValue({
      data: { url: "https://accounts.google.com/authorize" },
      error: null,
    });

    await expect(signInWithGoogle({ status: "idle" }, form("//evil.example"))).rejects.toThrow(
      "redirect:https://accounts.google.com/authorize",
    );
    expect(signInWithOAuth).toHaveBeenCalledWith({
      provider: "google",
      options: {
        redirectTo: "https://preview.cardwise.app/auth/callback?next=%2F&flow=google",
      },
    });
  });
});

import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  createSupabaseServerClient: vi.fn(),
  exchangeCodeForSession: vi.fn(),
}));

vi.mock("@/lib/env", () => ({ isMocking: false }));
vi.mock("@/lib/supabase/server", () => ({
  createSupabaseServerClient: mocks.createSupabaseServerClient,
}));

import { GET } from "./route";

describe("auth callback", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.createSupabaseServerClient.mockResolvedValue({
      auth: { exchangeCodeForSession: mocks.exchangeCodeForSession },
    });
    mocks.exchangeCodeForSession.mockResolvedValue({ error: null });
  });

  it("exchanges an OAuth code and returns to the same-site destination", async () => {
    const response = await GET(
      new NextRequest(
        "https://cardwise.example/auth/callback?code=oauth-code&flow=google&next=%2Fchats%2Fexample",
      ),
    );

    expect(mocks.exchangeCodeForSession).toHaveBeenCalledWith("oauth-code");
    expect(response.headers.get("location")).toBe("https://cardwise.example/chats/example");
  });

  it("falls back to the home page for an unsafe destination", async () => {
    const response = await GET(
      new NextRequest(
        "https://cardwise.example/auth/callback?code=oauth-code&flow=google&next=%2F%2Fevil.example",
      ),
    );

    expect(response.headers.get("location")).toBe("https://cardwise.example/");
  });

  it("returns failed Google callbacks to sign-in with a useful notice", async () => {
    const response = await GET(
      new NextRequest("https://cardwise.example/auth/callback?flow=google"),
    );

    expect(response.headers.get("location")).toBe("https://cardwise.example/sign-in?error=google");
  });
});

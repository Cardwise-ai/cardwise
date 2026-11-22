import { describe, expect, it, vi } from "vitest";
import { authOrigin } from "./site-origin";

describe("authOrigin", () => {
  it("prefers NEXT_PUBLIC_SITE_URL", () => {
    vi.stubEnv("NEXT_PUBLIC_SITE_URL", "https://cardwise.example/some/path");
    vi.stubEnv("VERCEL_ENV", "preview");
    vi.stubEnv("VERCEL_BRANCH_URL", "cardwise-web-git-dev-team.vercel.app");
    expect(authOrigin("https://cardwise-abc123-team.vercel.app")).toBe("https://cardwise.example");
  });

  it("sends Preview visitors on a deployment URL back to the stable branch URL", () => {
    vi.stubEnv("VERCEL_ENV", "preview");
    vi.stubEnv("VERCEL_BRANCH_URL", "cardwise-web-git-dev-team.vercel.app");
    expect(authOrigin("https://cardwise-abc123-team.vercel.app")).toBe(
      "https://cardwise-web-git-dev-team.vercel.app",
    );
  });

  it("never sends Production visitors to the main branch URL", () => {
    vi.stubEnv("VERCEL_ENV", "production");
    vi.stubEnv("VERCEL_BRANCH_URL", "cardwise-web-git-main-team.vercel.app");
    expect(authOrigin("https://cardwise-web.vercel.app")).toBe("https://cardwise-web.vercel.app");
  });

  it("falls back to the request origin outside Vercel", () => {
    expect(authOrigin("http://127.0.0.1:3000")).toBe("http://127.0.0.1:3000");
    expect(authOrigin(null)).toBeNull();
  });

  it.each([
    "javascript:alert(1)",
    "ftp://cardwise.example",
    "http://cardwise.example",
    "https://user:pass@cardwise.example",
    "not a url",
  ])("ignores the unusable origin %s", (origin) => {
    expect(authOrigin(origin)).toBeNull();
    vi.stubEnv("NEXT_PUBLIC_SITE_URL", origin);
    expect(authOrigin("http://localhost:3000")).toBe("http://localhost:3000");
  });
});

import { describe, expect, it } from "vitest";
import { safeNextPath } from "@/lib/auth/shared";
import { buildCsp } from "./csp";

const directives = (csp: string) =>
  Object.fromEntries(csp.split("; ").map((d) => [d.split(" ")[0], d.split(" ").slice(1)]));

describe("buildCsp", () => {
  const prod = directives(
    buildCsp({
      nonce: "abc123",
      isDev: false,
      apiUrl: "https://api.cardwise.example/v1",
      supabaseUrl: "https://project.supabase.co",
    }),
  );

  it("allows only nonced scripts and what they load", () => {
    expect(prod["script-src"]).toEqual(["'self'", "'nonce-abc123'", "'strict-dynamic'"]);
    expect(prod["script-src"]).not.toContain("'unsafe-inline'");
    expect(prod["script-src"]).not.toContain("'unsafe-eval'");
  });

  it("limits connections to the API and Supabase origins", () => {
    expect(prod["connect-src"]).toEqual([
      "'self'",
      "https://api.cardwise.example",
      "https://project.supabase.co",
    ]);
  });

  it("loads images only from Scryfall's card CDN", () => {
    expect(prod["img-src"]).toEqual(["'self'", "https://cards.scryfall.io"]);
  });

  it("blocks framing, plugins and service workers", () => {
    expect(prod["frame-ancestors"]).toEqual(["'none'"]);
    expect(prod["object-src"]).toEqual(["'none'"]);
    expect(prod["worker-src"]).toEqual(["'none'"]);
    expect(prod["base-uri"]).toEqual(["'self'"]);
  });

  it("adds eval only in development and the service worker only for mocks", () => {
    const dev = directives(
      buildCsp({
        nonce: "n",
        isDev: true,
        apiUrl: "http://127.0.0.1:8000",
        allowServiceWorker: true,
      }),
    );
    expect(dev["script-src"]).toContain("'unsafe-eval'");
    expect(dev["worker-src"]).toEqual(["'self'"]);
    expect(dev["connect-src"]).toEqual(["'self'", "http://127.0.0.1:8000"]);
  });

  it("skips origins it cannot parse", () => {
    const csp = directives(
      buildCsp({ nonce: "n", isDev: false, apiUrl: "not a url", supabaseUrl: "" }),
    );
    expect(csp["connect-src"]).toEqual(["'self'"]);
  });
});

describe("safeNextPath", () => {
  it.each([
    ["/chats/abc", "/chats/abc"],
    ["/", "/"],
    ["https://evil.example", "/"],
    ["//evil.example", "/"],
    ["/\\evil.example", "/"],
    ["javascript:alert(1)", "/"],
    ["/ok\r\nSet-Cookie: x", "/"],
    [undefined, "/"],
    [["/a", "/b"], "/"],
  ])("%j becomes %j", (input, expected) => {
    expect(safeNextPath(input)).toBe(expected);
  });
});

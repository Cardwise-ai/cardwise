import { describe, expect, it } from "vitest";
import { missingDarkTokens } from "./check-built-css.mjs";

const source = `
:root { color-scheme: light; }
:root[data-theme="dark"] {
  color-scheme: dark;
  --color-surface: #000;
  --color-rail: #111;
}
`;

describe("missingDarkTokens", () => {
  it("accepts minified CSS that carries the dark theme", () => {
    const built =
      ":root{color-scheme:light}:root[data-theme=dark]{color-scheme:dark;--color-surface:#000;--color-rail:#111}";
    expect(missingDarkTokens(source, built)).toEqual([]);
  });

  it("reports CSS built from an older globals.css", () => {
    const stale = ":root{--color-surface:#f3f4f1}";
    expect(missingDarkTokens(source, stale)).toEqual([
      "color-scheme: dark",
      '[data-theme="dark"]',
      "--color-rail",
    ]);
  });
});

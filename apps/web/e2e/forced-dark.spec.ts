import { inflateSync } from "node:zlib";
import { expect, type Page, test } from "@playwright/test";
import { THEME_COLORS } from "../src/lib/theme";

// Chrome's "Auto Dark Mode for Web Contents". The headless shell ignores the flag, so this file
// runs the full Chromium build.
test.use({
  channel: "chromium",
  launchOptions: { args: ["--enable-features=WebContentsForceDark"] },
});
/** Reads one screen pixel as #rrggbb. */
async function pixel(page: Page, x: number, y: number): Promise<string> {
  const png = await page.screenshot({ clip: { x, y, width: 1, height: 1 } });
  const chunks: Buffer[] = [];
  for (let offset = 8; offset < png.length;) {
    const length = png.readUInt32BE(offset);
    if (png.toString("ascii", offset + 4, offset + 8) === "IDAT") {
      chunks.push(png.subarray(offset + 8, offset + 8 + length));
    }
    offset += 12 + length;
  }
  const [, r, g, b] = inflateSync(Buffer.concat(chunks));
  return `#${[r, g, b].map((value) => (value ?? 0).toString(16).padStart(2, "0")).join("")}`;
}

test.describe("with the browser's automatic dark mode on", () => {
  for (const [os, saved, expected] of [
    ["light", "light", THEME_COLORS.light],
    ["dark", "light", THEME_COLORS.light],
    ["light", null, THEME_COLORS.light],
    ["light", "dark", THEME_COLORS.dark],
  ] as const) {
    test(`OS ${os} with ${saved ?? "system"} chosen keeps our own palette`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: os });
      await page.goto("/sign-in");
      await page.evaluate((value) => {
        if (value) localStorage.setItem("cardwise.theme", value);
      }, saved);
      await page.reload();
      await page.evaluate(() => {
        const probe = document.createElement("div");
        probe.style.cssText =
          "position:fixed;left:0;top:0;width:8px;height:8px;z-index:2147483647;background:var(--color-surface)";
        document.body.append(probe);
      });
      await expect.poll(() => pixel(page, 4, 4)).toBe(expected);
    });
  }
});

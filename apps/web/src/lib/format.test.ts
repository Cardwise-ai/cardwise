import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { describeSymbol, parseSymbols } from "@/components/cards/mana";
import type { Chat } from "@/lib/api/client";
import { contrastRatio, darkPalette, palette } from "./contrast";
import { chatTitle, groupChats, rateLimitMessage } from "./format";

describe("design tokens", () => {
  const css = readFileSync(resolve(process.cwd(), "src/app/globals.css"), "utf8");

  it("match the palette in globals.css", () => {
    for (const [name, hex] of Object.entries(palette)) {
      expect(css.toLowerCase()).toContain(`--color-${name}: ${hex}`);
    }
  });

  it("match the night-table palette in globals.css", () => {
    const darkTokens = /:root\[data-theme="dark"\]\s*{([\s\S]*?)\n}/.exec(css)?.[1] ?? "";
    for (const [name, hex] of Object.entries(darkPalette)) {
      expect(darkTokens.toLowerCase()).toContain(`--color-${name}: ${hex}`);
    }
  });

  it.each([
    ["ink", "panel"],
    ["ink", "surface"],
    ["muted", "panel"],
    ["muted", "surface"],
    ["muted", "hover"],
    ["accent", "panel"],
    ["accent", "surface"],
    ["accent", "accent-wash"],
    ["panel", "accent"],
    ["rail-ink", "rail"],
    ["rail-muted", "rail"],
    ["action-ink", "accent"],
    ["action-ink", "accent-strong"],
    ["danger-ink", "danger"],
    ["danger", "danger-wash"],
  ] as const)("%s on %s meets 4.5:1", (text, background) => {
    expect(contrastRatio(palette[text], palette[background])).toBeGreaterThanOrEqual(4.5);
  });

  it.each([
    ["ink", "surface"],
    ["ink", "panel"],
    ["muted", "surface"],
    ["muted", "panel"],
    ["accent", "surface"],
    ["accent", "panel"],
    ["accent", "accent-wash"],
    ["rail-ink", "rail"],
    ["rail-muted", "rail"],
    ["action-ink", "accent"],
    ["action-ink", "accent-strong"],
    ["danger", "danger-wash"],
    ["danger-ink", "danger"],
  ] as const)("dark %s on %s meets 4.5:1", (text, background) => {
    expect(contrastRatio(darkPalette[text], darkPalette[background])).toBeGreaterThanOrEqual(4.5);
  });
});

describe("mana symbols", () => {
  it("parses a cost into symbols", () => {
    expect(parseSymbols("{2}{W/U}{B/P}{X}")).toEqual(["2", "W/U", "B/P", "X"]);
    expect(parseSymbols("")).toEqual([]);
  });

  it.each([
    ["G", "green"],
    ["3", "3 generic"],
    ["W/U", "white or blue"],
    ["2/W", "2 generic or white"],
    ["B/P", "Phyrexian black"],
    ["T", "tap"],
    ["C", "colorless"],
  ])("describes {%s} as %s", (symbol, words) => {
    expect(describeSymbol(symbol)).toBe(words);
  });
});

describe("groupChats", () => {
  const now = new Date(2026, 4, 20, 15, 0);
  const chat = (title: string, updated: Date): Chat => ({
    id: crypto.randomUUID(),
    title,
    created_at: updated.toISOString(),
    updated_at: updated.toISOString(),
  });

  it("groups by today, the previous week and earlier, skipping empty groups", () => {
    const groups = groupChats(
      [
        chat("this morning", new Date(2026, 4, 20, 8, 0)),
        chat("last night", new Date(2026, 4, 19, 23, 30)),
        chat("months ago", new Date(2026, 0, 2)),
      ],
      now,
    );
    expect(groups.map((g) => [g.label, g.chats.map((c) => c.title)])).toEqual([
      ["Today", ["this morning"]],
      ["Previous 7 days", ["last night"]],
      ["Earlier", ["months ago"]],
    ]);
    expect(groupChats([], now)).toEqual([]);
  });
});

describe("rateLimitMessage", () => {
  it("says when the reader can try again", () => {
    const now = new Date(Date.UTC(2026, 4, 20, 14, 0));
    expect(rateLimitMessage(1260, now, "en-GB")).toMatch(
      /^Too many messages this hour\. Try again at \d{2}:21\.$/,
    );
    expect(rateLimitMessage(null, now)).toBe("Too many messages this hour. Try again later.");
  });

  it("tells a short wait apart from the hourly limit", () => {
    expect(rateLimitMessage(5)).toMatch(/still answering another message.*few seconds\.$/);
  });
});

describe("chatTitle", () => {
  it("uses a short first message as it is, on one line", () => {
    expect(chatTitle("  Ramp for\n  Esika?  ")).toBe("Ramp for Esika?");
  });

  it("cuts a long first message at a word and marks the cut", () => {
    expect(
      chatTitle(
        "What are the best free sacrifice outlets for Meren of Clan Nel Toth in a budget list?",
      ),
    ).toBe("What are the best free sacrifice outlets for Meren of Clan…");
  });

  it("cuts a single long word at the limit", () => {
    expect(chatTitle("a".repeat(80))).toBe(`${"a".repeat(59)}…`);
  });
});

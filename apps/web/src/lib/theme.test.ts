import { afterEach, describe, expect, it, vi } from "vitest";
import { darkPalette, palette } from "./contrast";
import { readThemeMode, resolveTheme, THEME_BOOTSTRAP, THEME_STORAGE_KEY } from "./theme";

describe("theme preference", () => {
  it.each([
    ["light", "light"],
    ["dark", "dark"],
    ["system", "system"],
    ["unknown", "system"],
    [null, "system"],
  ] as const)("reads %s as %s", (value, expected) => {
    expect(readThemeMode(value)).toBe(expected);
  });

  it("uses the system preference only while the mode is system", () => {
    expect(resolveTheme("system", true)).toBe("dark");
    expect(resolveTheme("system", false)).toBe("light");
    expect(resolveTheme("light", true)).toBe("light");
    expect(resolveTheme("dark", false)).toBe("dark");
  });
});

describe("theme bootstrap", () => {
  function runBootstrap(saved: string | null, systemDark: boolean) {
    document.head.innerHTML = [
      '<meta name="theme-color" media="(prefers-color-scheme: light)" content="#000000">',
      '<meta name="theme-color" media="(prefers-color-scheme: dark)" content="#000000">',
    ].join("");
    const root = document.documentElement;
    root.removeAttribute("data-theme");
    root.removeAttribute("style");
    if (saved) localStorage.setItem(THEME_STORAGE_KEY, saved);
    else localStorage.removeItem(THEME_STORAGE_KEY);
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: query === "(prefers-color-scheme: dark)" && systemDark,
    }));
    new Function(THEME_BOOTSTRAP)();
    const colors = [...document.querySelectorAll('meta[name="theme-color"]')].map((meta) =>
      meta.getAttribute("content"),
    );
    return { theme: root.dataset.theme, colorScheme: root.style.colorScheme, colors };
  }

  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it("paints a saved dark choice on a light system with dark browser chrome", () => {
    expect(runBootstrap("dark", false)).toEqual({
      theme: "dark",
      colorScheme: "dark",
      colors: [darkPalette.surface, darkPalette.surface],
    });
  });

  it("opts a resolved light theme out of the browser's automatic dark mode", () => {
    expect(runBootstrap("light", true)).toEqual({
      theme: "light",
      colorScheme: "only light",
      colors: [palette.surface, palette.surface],
    });
    expect(runBootstrap(null, false).colorScheme).toBe("only light");
  });
});

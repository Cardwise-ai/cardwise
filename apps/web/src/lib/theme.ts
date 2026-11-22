import { darkPalette, palette } from "./contrast";

export type ThemeMode = "system" | "light" | "dark";
export type ResolvedTheme = "light" | "dark";

export const THEME_STORAGE_KEY = "cardwise.theme";

/** Browser chrome colors (`<meta name="theme-color">`) match the page surface. */
export const THEME_COLORS: Readonly<Record<ResolvedTheme, string>> = {
  light: palette.surface,
  dark: darkPalette.surface,
};

/**
 * Points <html> and the browser chrome at a theme. It is serialized into THEME_BOOTSTRAP, so it
 * must stay self-contained: no imports, closures or helpers.
 *
 * "only light" keeps Chrome's Auto Dark Mode (and similar features) from repainting a light theme
 * the user chose or their system asked for; we ship our own dark theme instead.
 */
export function applyTheme(
  mode: ThemeMode,
  systemDark: boolean,
  colors: Readonly<Record<ResolvedTheme, string>>,
): void {
  const theme = mode === "system" ? (systemDark ? "dark" : "light") : mode;
  const root = document.documentElement;
  root.dataset.themeMode = mode;
  root.dataset.theme = theme;
  root.style.colorScheme = theme === "dark" ? "dark" : "only light";
  document.querySelectorAll('meta[name="theme-color"]').forEach((meta) => {
    meta.setAttribute("content", colors[theme]);
  });
}

/** Runs inline in <head> before first paint so a saved preference never flashes the other palette. */
export const THEME_BOOTSTRAP = `(() => {
  let saved = null;
  try {
    saved = localStorage.getItem(${JSON.stringify(THEME_STORAGE_KEY)});
  } catch {
    saved = null;
  }
  const mode = saved === "light" || saved === "dark" ? saved : "system";
  (${applyTheme.toString()})(mode, matchMedia("(prefers-color-scheme: dark)").matches, ${JSON.stringify(THEME_COLORS)});
})();`;

export function readThemeMode(value: string | null): ThemeMode {
  return value === "light" || value === "dark" ? value : "system";
}

export function resolveTheme(mode: ThemeMode, systemDark: boolean): ResolvedTheme {
  return mode === "system" ? (systemDark ? "dark" : "light") : mode;
}

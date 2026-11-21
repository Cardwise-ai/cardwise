export type ThemeMode = "system" | "light" | "dark";

export const THEME_STORAGE_KEY = "cardwise.theme";

/** Runs before paint so a saved preference never flashes the opposite palette. */
export const THEME_BOOTSTRAP = `(() => {
  const root = document.documentElement;
  const systemDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  let saved = null;
  try {
    saved = localStorage.getItem("${THEME_STORAGE_KEY}");
  } catch {
    saved = null;
  }
  const mode = saved === "light" || saved === "dark" ? saved : "system";
  root.dataset.themeMode = mode;
  root.dataset.theme = mode === "system" ? (systemDark ? "dark" : "light") : mode;
})();`;

export function readThemeMode(value: string | null): ThemeMode {
  return value === "light" || value === "dark" ? value : "system";
}

export function resolveTheme(mode: ThemeMode, systemDark: boolean): "light" | "dark" {
  return mode === "system" ? (systemDark ? "dark" : "light") : mode;
}

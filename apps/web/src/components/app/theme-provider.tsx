"use client";

import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  applyTheme as applyThemeTo,
  readThemeMode,
  THEME_COLORS,
  THEME_STORAGE_KEY,
  type ThemeMode,
} from "@/lib/theme";

interface ThemeContextValue {
  mode: ThemeMode;
  setMode: (mode: ThemeMode) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

function savedMode(): ThemeMode {
  try {
    return readThemeMode(window.localStorage.getItem(THEME_STORAGE_KEY));
  } catch {
    return "system";
  }
}

function applyTheme(mode: ThemeMode, systemDark: boolean) {
  applyThemeTo(mode, systemDark, THEME_COLORS);
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>("system");

  useEffect(() => {
    const preference = window.matchMedia("(prefers-color-scheme: dark)");
    const sync = () => {
      const current = savedMode();
      setModeState(current);
      applyTheme(current, preference.matches);
    };
    const onPreferenceChange = () => {
      if (savedMode() === "system") applyTheme("system", preference.matches);
    };
    const onStorage = (event: StorageEvent) => {
      if (event.key === THEME_STORAGE_KEY || event.key === null) sync();
    };

    sync();
    preference.addEventListener("change", onPreferenceChange);
    window.addEventListener("storage", onStorage);
    return () => {
      preference.removeEventListener("change", onPreferenceChange);
      window.removeEventListener("storage", onStorage);
    };
  }, []);

  const setMode = useCallback((next: ThemeMode) => {
    try {
      if (next === "system") window.localStorage.removeItem(THEME_STORAGE_KEY);
      else window.localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      // The active tab still follows the chosen theme when storage is unavailable.
    }
    setModeState(next);
    applyTheme(next, window.matchMedia("(prefers-color-scheme: dark)").matches);
  }, []);

  const value = useMemo(() => ({ mode, setMode }), [mode, setMode]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const value = useContext(ThemeContext);
  if (!value) throw new Error("useTheme must be used inside <ThemeProvider>");
  return value;
}

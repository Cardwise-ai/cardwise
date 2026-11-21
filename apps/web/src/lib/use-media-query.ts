import { useSyncExternalStore } from "react";

/** Tracks a media query. Renders with `false` on the server and before hydration. */
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const list = window.matchMedia(query);
      list.addEventListener("change", onChange);
      return () => list.removeEventListener("change", onChange);
    },
    () => window.matchMedia(query).matches,
    () => false,
  );
}

/** Matches the spec breakpoints: the card panel docks at 1024px, the chat list at 768px. */
export const WIDE = "(min-width: 1024px)";
export const MEDIUM = "(min-width: 768px)";

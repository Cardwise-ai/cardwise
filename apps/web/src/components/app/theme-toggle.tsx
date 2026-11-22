"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { cx } from "@/lib/cx";
import { type ThemeMode } from "@/lib/theme";
import { useTheme } from "./theme-provider";

const modes: ThemeMode[] = ["system", "light", "dark"];
const labels: Record<ThemeMode, string> = {
  system: "System",
  light: "Light",
  dark: "Dark",
};
const icons = {
  system: Monitor,
  light: Sun,
  dark: Moon,
};

export function ThemeToggle({
  variant = "surface",
  className,
}: {
  variant?: "surface" | "rail";
  className?: string;
}) {
  const { mode, setMode } = useTheme();
  const next = modes[(modes.indexOf(mode) + 1) % modes.length]!;
  const Icon = icons[mode];

  return (
    <button
      type="button"
      aria-label={`Theme: ${labels[mode]}. Change to ${labels[next]}.`}
      title={`Change theme from ${labels[mode]} to ${labels[next]}`}
      onClick={() => setMode(next)}
      className={cx(
        "inline-flex min-h-9 items-center gap-2 rounded-pill border px-3.5 text-sm font-semibold transition-colors focus-visible:outline-offset-2",
        variant === "rail"
          ? "border-rail-rule text-rail-ink hover:bg-rail-hover"
          : "border-rule bg-panel text-ink hover:bg-hover",
        className,
      )}
    >
      <Icon aria-hidden className="size-4" />
      <span>Theme: {labels[mode]}</span>
    </button>
  );
}

/** WCAG 2.x relative luminance and contrast ratio for #rrggbb colors. */

function channel(value: number): number {
  const c = value / 255;
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

export function luminance(hex: string): number {
  const match = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex);
  if (!match) throw new Error(`Expected #rrggbb, got ${hex}`);
  const [r, g, b] = [match[1], match[2], match[3]].map((part) => parseInt(part ?? "0", 16));
  return 0.2126 * channel(r ?? 0) + 0.7152 * channel(g ?? 0) + 0.0722 * channel(b ?? 0);
}

export function contrastRatio(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}

/** The palette from spec §8.2, plus the derived states used in components. */
export const palette = {
  surface: "#f3f4f1",
  panel: "#ffffff",
  ink: "#22262b",
  muted: "#5d646c",
  rule: "#d6d9d4",
  accent: "#2f5d50",
  "accent-strong": "#244a40",
  "accent-wash": "#e7eeea",
  hover: "#e9ebe6",
  danger: "#9c2f2a",
  "danger-wash": "#f8ecea",
} as const;

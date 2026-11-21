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

/** The Cardwise playmat-and-cardstock palette, plus the derived states used in components. */
export const palette = {
  surface: "#e6ede5",
  panel: "#fbfaf4",
  ink: "#1b2a25",
  muted: "#4e625a",
  rule: "#c7d3c9",
  "rule-strong": "#9cab9f",
  accent: "#1d4b40",
  "accent-strong": "#14382f",
  "accent-wash": "#d9e7dd",
  hover: "#dde7dd",
  placeholder: "#e1e9e1",
  brass: "#b18a3c",
  river: "#36798a",
  danger: "#9c2f2a",
  "danger-wash": "#f8ecea",
} as const;

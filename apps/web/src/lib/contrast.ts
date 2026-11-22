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
  "action-ink": "#ffffff",
  "danger-ink": "#ffffff",
  overlay: "#10211c",
  rail: "#1d4b40",
  "rail-ink": "#fbfaf4",
  "rail-muted": "#c8d8ca",
  "rail-rule": "#507266",
  "rail-hover": "#2a5a4d",
  danger: "#9c2f2a",
  "danger-wash": "#f8ecea",
} as const;

export const darkPalette = {
  surface: "#15241f",
  panel: "#20322b",
  ink: "#e7ede6",
  muted: "#b5c4b8",
  rule: "#3d5147",
  "rule-strong": "#63776b",
  accent: "#91c9a6",
  "accent-strong": "#a5d7b5",
  "accent-wash": "#294539",
  hover: "#2a3b33",
  placeholder: "#25372f",
  brass: "#c6aa73",
  river: "#8fc5d5",
  "action-ink": "#14231d",
  "danger-ink": "#2d1716",
  overlay: "#071410",
  rail: "#10221d",
  "rail-ink": "#f3f4e9",
  "rail-muted": "#bdccc0",
  "rail-rule": "#34493f",
  "rail-hover": "#1c3229",
  danger: "#f29a8f",
  "danger-strong": "#ffc1b8",
  "danger-wash": "#4a2c2a",
} as const;

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

/** Ultraviolet on cool paper, plus the derived states used in components. See docs/style-guide.md. */
export const palette = {
  surface: "#f4f2f7",
  panel: "#ffffff",
  ink: "#18141f",
  muted: "#5b5468",
  rule: "#ddd8e5",
  "rule-strong": "#8b829c",
  accent: "#5a2ec0",
  "accent-strong": "#46209e",
  "accent-wash": "#ece6fb",
  hover: "#ece9f2",
  placeholder: "#e6e2ee",
  signal: "#d6c6ff",
  "action-ink": "#ffffff",
  "danger-ink": "#ffffff",
  overlay: "#140a2b",
  rail: "#24124f",
  "rail-ink": "#ffffff",
  "rail-muted": "#cdc2ea",
  "rail-rule": "#46357d",
  "rail-hover": "#35226e",
  danger: "#b0261f",
  "danger-strong": "#8a1c17",
  "danger-wash": "#fcedeb",
} as const;

/** True black page and rail, one raised neutral for fields, and a lavender accent. */
export const darkPalette = {
  surface: "#000000",
  panel: "#141414",
  ink: "#f4f2f7",
  muted: "#a9a3b5",
  rule: "#2b2b2e",
  "rule-strong": "#6c6874",
  accent: "#b79cff",
  "accent-strong": "#cdbbff",
  "accent-wash": "#21183a",
  hover: "#1c1c1e",
  placeholder: "#161616",
  signal: "#b79cff",
  "action-ink": "#000000",
  "danger-ink": "#000000",
  overlay: "#000000",
  rail: "#000000",
  "rail-ink": "#f4f2f7",
  "rail-muted": "#a9a3b5",
  "rail-rule": "#262628",
  "rail-hover": "#17151c",
  danger: "#ff8f85",
  "danger-strong": "#ffb8b1",
  "danger-wash": "#2b1311",
} as const;

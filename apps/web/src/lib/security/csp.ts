export const CARD_IMAGE_ORIGIN = "https://cards.scryfall.io";
export const CSP_REPORT_PATH = "/csp-report";

/** Report-Only until a clean week of reports (spec E13), then switch to enforcing. */
export const CSP_ENFORCE = false;

export const cspHeaderName = CSP_ENFORCE
  ? "Content-Security-Policy"
  : "Content-Security-Policy-Report-Only";

export interface CspOptions {
  nonce: string;
  isDev: boolean;
  apiUrl: string;
  supabaseUrl?: string | undefined;
  /** MSW registers a service worker in mock mode. */
  allowServiceWorker?: boolean;
}

function originOf(url: string | undefined): string | null {
  if (!url) return null;
  try {
    const { origin } = new URL(url);
    return origin === "null" ? null : origin;
  } catch {
    return null;
  }
}

export function createNonce(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return btoa(String.fromCharCode(...bytes));
}

export function buildCsp(options: CspOptions): string {
  const { nonce, isDev } = options;
  const connect = new Set(["'self'"]);
  for (const url of [options.apiUrl, options.supabaseUrl]) {
    const origin = originOf(url);
    if (origin) connect.add(origin);
  }

  const directives: Array<[string, string[]]> = [
    ["default-src", ["'self'"]],
    // 'strict-dynamic' lets nonced Next.js bundles load their chunks; React needs eval only in dev.
    [
      "script-src",
      ["'self'", `'nonce-${nonce}'`, "'strict-dynamic'", ...(isDev ? ["'unsafe-eval'"] : [])],
    ],
    // Radix positions popovers with inline style attributes, which a nonce cannot cover.
    ["style-src", ["'self'", "'unsafe-inline'"]],
    ["img-src", ["'self'", CARD_IMAGE_ORIGIN]],
    ["font-src", ["'self'"]],
    ["connect-src", [...connect]],
    ["worker-src", options.allowServiceWorker ? ["'self'"] : ["'none'"]],
    ["frame-src", ["'none'"]],
    ["object-src", ["'none'"]],
    ["base-uri", ["'self'"]],
    ["form-action", ["'self'"]],
    ["frame-ancestors", ["'none'"]],
    ["report-uri", [CSP_REPORT_PATH]],
    ["report-to", ["csp"]],
  ];
  if (CSP_ENFORCE && !isDev) directives.push(["upgrade-insecure-requests", []]);

  return directives.map(([name, values]) => [name, ...values].join(" ")).join("; ");
}

/** Headers that do not depend on the request. Applied to every route in next.config.ts. */
export const staticSecurityHeaders: ReadonlyArray<{ key: string; value: string }> = [
  { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains; preload" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
  {
    key: "Permissions-Policy",
    value:
      "accelerometer=(), autoplay=(), browsing-topics=(), camera=(), display-capture=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), midi=(), payment=(), usb=()",
  },
];

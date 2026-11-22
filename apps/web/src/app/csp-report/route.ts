const MAX_BODY_BYTES = 16_384;

interface Violation {
  directive: string;
  blocked: string;
  page: string;
}

function stripQuery(value: unknown): string {
  if (typeof value !== "string") return "";
  try {
    const url = new URL(value);
    return url.origin + url.pathname;
  } catch {
    return value.slice(0, 100);
  }
}

function toViolation(raw: Record<string, unknown>): Violation {
  return {
    directive: String(
      raw["effectiveDirective"] ?? raw["effective-directive"] ?? raw["violated-directive"] ?? "",
    ),
    blocked: stripQuery(raw["blockedURL"] ?? raw["blocked-uri"]),
    page: stripQuery(raw["documentURL"] ?? raw["document-uri"]),
  };
}

/** Collects CSP reports during the Report-Only period. Logs only directive and URLs without queries. */
export async function POST(request: Request) {
  const text = await request.text();
  if (text.length > MAX_BODY_BYTES) return new Response(null, { status: 413 });
  try {
    const body: unknown = JSON.parse(text);
    const reports = Array.isArray(body) ? body : [body];
    for (const report of reports.slice(0, 20)) {
      if (!report || typeof report !== "object") continue;
      const r = report as Record<string, unknown>;
      const raw = (r["csp-report"] ?? r["body"] ?? r) as Record<string, unknown>;
      console.warn(JSON.stringify({ event: "csp_violation", ...toViolation(raw) }));
    }
  } catch {
    return new Response(null, { status: 400 });
  }
  return new Response(null, { status: 204 });
}

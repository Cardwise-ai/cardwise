import createClient, { type Client, type Middleware } from "openapi-fetch";
import type { components, paths } from "./schema";

export type Schemas = components["schemas"];
export type Chat = Schemas["ChatOut"];
export type ChatPage = Schemas["ChatPage"];
export type Message = Schemas["MessageOut"];
export type CardRef = Schemas["CardRef"];
export type CardDetail = Schemas["CardDetail"];
export type CardFace = Schemas["CardFace"];
export type CardSummary = Schemas["CardSummary"];
export type Color = Schemas["Color"];
export type ErrorCode = Schemas["ErrorDetail"]["code"];

export type ApiClient = Client<paths>;

export interface ApiClientOptions {
  baseUrl: string;
  /** Returns the Supabase access token, or null when signed out. */
  getAccessToken: () => Promise<string | null>;
  /** Forces a token refresh after a 401. Returns the new token, or null when that isn't possible. */
  refreshAccessToken?: () => Promise<string | null>;
  /** Called when a request is still unauthorized after any refresh: the session has ended. */
  onUnauthorized?: () => void;
}

export function createApiClient({
  baseUrl,
  getAccessToken,
  refreshAccessToken,
  onUnauthorized,
}: ApiClientOptions): ApiClient {
  // Resolve fetch per call so test interceptors installed later still apply.
  async function send(request: Request): Promise<Response> {
    // A token can expire between reading it and the API checking it, so a 401 gets one retry
    // with a freshly refreshed token before the session counts as ended.
    const retry =
      refreshAccessToken && request.headers.has("Authorization") ? request.clone() : null;
    const response = await globalThis.fetch(request);
    if (response.status !== 401) return response;
    if (retry && refreshAccessToken) {
      const token = await refreshAccessToken().catch(() => null);
      if (token) {
        const headers = new Headers(retry.headers);
        headers.set("Authorization", `Bearer ${token}`);
        const second = await globalThis.fetch(new Request(retry, { headers }));
        if (second.status !== 401) return second;
        onUnauthorized?.();
        return second;
      }
    }
    onUnauthorized?.();
    return response;
  }

  const client = createClient<paths>({ baseUrl, fetch: send });
  const auth: Middleware = {
    async onRequest({ request }) {
      const token = await getAccessToken();
      if (token) request.headers.set("Authorization", `Bearer ${token}`);
      return request;
    },
  };
  client.use(auth);
  return client;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: ErrorCode | "network";
  readonly requestId: string | null;
  /** Seconds from the Retry-After header on 429 responses. */
  readonly retryAfter: number | null;

  constructor(init: {
    status: number;
    code: ApiError["code"];
    message: string;
    requestId?: string | null;
    retryAfter?: number | null;
  }) {
    super(init.message);
    this.name = "ApiError";
    this.status = init.status;
    this.code = init.code;
    this.requestId = init.requestId ?? null;
    this.retryAfter = init.retryAfter ?? null;
  }
}

const fallbackCodes: Record<number, ErrorCode> = {
  400: "bad_request",
  401: "unauthorized",
  404: "not_found",
  422: "bad_request",
  429: "rate_limited",
  501: "not_implemented",
};

export function toApiError(response: Response, body: unknown): ApiError {
  const detail =
    body && typeof body === "object" && "error" in body
      ? (body as { error?: Partial<Schemas["ErrorDetail"]> }).error
      : undefined;
  const retryHeader = response.headers.get("retry-after");
  const retryAfter = retryHeader && /^\d+$/.test(retryHeader) ? Number(retryHeader) : null;
  return new ApiError({
    status: response.status,
    code: detail?.code ?? fallbackCodes[response.status] ?? "internal",
    message: detail?.message ?? "Something went wrong on our side.",
    requestId: detail?.request_id ?? response.headers.get("x-request-id"),
    retryAfter,
  });
}

/** Returns `data` or throws an ApiError. Network failures become code "network". */
export async function unwrap<T>(
  call: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  let result: Awaited<typeof call>;
  try {
    result = await call;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError({ status: 0, code: "network", message: "Can't reach Cardwise." });
  }
  if (!result.response.ok) throw toApiError(result.response, result.error);
  return result.data as T;
}

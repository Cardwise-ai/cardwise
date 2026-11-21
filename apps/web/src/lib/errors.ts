import { ApiError } from "@/lib/api/client";
import type { StreamErrorCode } from "@/lib/stream/events";
import { rateLimitMessage } from "./format";

/** Copy for a failed request: what happened and what to do next. */
export function describeError(error: unknown, now = new Date()): string {
  if (!(error instanceof ApiError)) return "Something went wrong. Try again.";
  switch (error.code) {
    case "network":
      return "Can't reach Cardwise. Check your connection and try again.";
    case "unauthorized":
      return "Your session has ended. Sign in again to continue.";
    case "not_found":
      return "This chat no longer exists.";
    case "rate_limited":
      return rateLimitMessage(error.retryAfter, now);
    case "bad_request":
      return error.message;
    case "not_implemented":
      return "This isn't available yet.";
    default:
      return "Something went wrong on our side. Try again.";
  }
}

/** Copy for an `error` event that ends an answer stream. */
export function describeStreamError(code: StreamErrorCode): string {
  switch (code) {
    case "rate_limited":
      return "You've reached today's answer limit. Try again tomorrow.";
    case "model_unavailable":
      return "The answer stopped because the model is busy. Try again in a minute.";
    default:
      return "The answer stopped because of a problem on our side. Try again.";
  }
}

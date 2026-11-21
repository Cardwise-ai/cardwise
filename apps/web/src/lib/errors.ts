import { ApiError } from "@/lib/api/client";
import type { StreamErrorCode } from "@/lib/stream/events";
import { rateLimitMessage } from "./format";

/** What the failed request was about, so 404 and 501 can say what is missing. */
export type ErrorSubject = "chat" | "send" | "card";

/** Copy for a failed request: what happened and what to do next. */
export function describeError(
  error: unknown,
  subject: ErrorSubject = "chat",
  now = new Date(),
): string {
  if (!(error instanceof ApiError)) return "Something went wrong. Try again.";
  switch (error.code) {
    case "network":
      return "Can't reach Cardwise. Check your connection and try again.";
    case "unauthorized":
      return "Your session has ended. Sign in again to continue.";
    case "not_found":
      return subject === "card"
        ? "This card isn't in Cardwise's card data."
        : "This chat no longer exists.";
    case "rate_limited":
      return rateLimitMessage(error.retryAfter, now);
    case "bad_request":
      return error.message;
    case "not_implemented":
      if (subject === "send") return "Answers aren't switched on for this server yet.";
      if (subject === "card") return "Card details aren't available on this server yet.";
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

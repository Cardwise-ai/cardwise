import { parseStreamEvent, type StreamEvent } from "./events";
import { readSseData } from "./sse";

export interface ReadEventsOptions {
  signal?: AbortSignal;
  /** Called for events that were dropped: unknown types or payloads that failed validation. */
  onSkipped?: (reason: string) => void;
}

/** Validated stream events from a `POST /v1/chats/{id}/messages` response body. */
export async function* readStreamEvents(
  body: ReadableStream<Uint8Array>,
  options: ReadEventsOptions = {},
): AsyncGenerator<StreamEvent, void, undefined> {
  for await (const data of readSseData(body, options.signal)) {
    const parsed = parseStreamEvent(data);
    if (parsed.kind === "event") yield parsed.event;
    else
      options.onSkipped?.(
        parsed.kind === "unknown" ? `unknown type ${parsed.type}` : parsed.reason,
      );
  }
}

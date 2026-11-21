/**
 * A minimal server-sent events reader (WHATWG HTML §9.2.6) over a fetch body.
 * Yields the data of each dispatched event. Comment lines (heartbeats) and fields
 * other than `data` are ignored, as is any event left without a terminating blank line.
 */
export async function* readSseData(
  body: ReadableStream<Uint8Array>,
  signal?: AbortSignal,
): AsyncGenerator<string, void, undefined> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let data: string[] = [];
  let first = true;

  const onAbort = () => {
    reader.cancel().catch(() => {});
  };
  signal?.addEventListener("abort", onAbort, { once: true });

  let finished = false;
  try {
    while (true) {
      if (signal?.aborted) throw abortError(signal);
      const { value, done } = await reader.read();
      if (signal?.aborted) throw abortError(signal);
      if (done) {
        finished = true;
        break;
      }

      buffer += decoder.decode(value, { stream: true });
      if (first && buffer.length > 0) {
        if (buffer.charCodeAt(0) === 0xfeff) buffer = buffer.slice(1);
        first = false;
      }

      // A trailing "\r" may be the first half of "\r\n"; wait for the next chunk to decide.
      let start = 0;
      for (let i = 0; i < buffer.length; i++) {
        const ch = buffer[i];
        if (ch !== "\n" && ch !== "\r") continue;
        if (ch === "\r" && i === buffer.length - 1) break;
        const line = buffer.slice(start, i);
        if (ch === "\r" && buffer[i + 1] === "\n") i++;
        start = i + 1;

        if (line === "") {
          if (data.length > 0) {
            yield data.join("\n");
            // The consumer may have aborted while this event was being handled.
            if (signal?.aborted) throw abortError(signal);
          }
          data = [];
          continue;
        }
        if (line.startsWith(":")) continue;
        const colon = line.indexOf(":");
        const field = colon === -1 ? line : line.slice(0, colon);
        if (field !== "data") continue;
        let fieldValue = colon === -1 ? "" : line.slice(colon + 1);
        if (fieldValue.startsWith(" ")) fieldValue = fieldValue.slice(1);
        data.push(fieldValue);
      }
      buffer = buffer.slice(start);
    }
  } finally {
    signal?.removeEventListener("abort", onAbort);
    // The consumer stopped early or the read failed: tell the server we are gone.
    if (!finished) await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

function abortError(signal: AbortSignal): unknown {
  return signal.reason ?? new DOMException("The operation was aborted.", "AbortError");
}

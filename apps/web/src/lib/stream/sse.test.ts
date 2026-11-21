import { describe, expect, it } from "vitest";
import { readSseData } from "./sse";

const encoder = new TextEncoder();

/** A body that delivers the given chunks one read at a time. */
function bodyOf(chunks: Array<string | Uint8Array>): ReadableStream<Uint8Array> {
  let index = 0;
  return new ReadableStream({
    pull(controller) {
      const chunk = chunks[index++];
      if (chunk === undefined) controller.close();
      else controller.enqueue(typeof chunk === "string" ? encoder.encode(chunk) : chunk);
    },
  });
}

async function collect(chunks: Array<string | Uint8Array>): Promise<string[]> {
  const out: string[] = [];
  for await (const data of readSseData(bodyOf(chunks))) out.push(data);
  return out;
}

/** Every way to cut `text` into two chunks. */
function allSplits(text: string): string[][] {
  return Array.from({ length: text.length + 1 }, (_, i) => [text.slice(0, i), text.slice(i)]);
}

describe("readSseData", () => {
  it("yields the data of each event", async () => {
    expect(await collect(['data: {"a":1}\n\ndata: {"b":2}\n\n'])).toEqual(['{"a":1}', '{"b":2}']);
  });

  it("gives the same events however the bytes are split", async () => {
    const text =
      'data: {"type":"text","text":"Viscera"}\r\n\r\n: heartbeat\n\ndata: second\r\rdata: third\n\n';
    for (const split of allSplits(text)) {
      expect(await collect(split)).toEqual(['{"type":"text","text":"Viscera"}', "second", "third"]);
    }
  });

  it("reassembles multi-byte characters split across chunks", async () => {
    const bytes = encoder.encode("data: Fire // Ice — Æther\n\n");
    const cut = bytes.indexOf(0xe2) + 1;
    expect(await collect([bytes.slice(0, cut), bytes.slice(cut)])).toEqual(["Fire // Ice — Æther"]);
  });

  it("ignores heartbeats, comments and fields other than data", async () => {
    const text = ": ping\n\nevent: text\nid: 4\nretry: 10\ndata: kept\n\n:\n\n";
    expect(await collect([text])).toEqual(["kept"]);
  });

  it("joins multi-line data with newlines and strips one leading space", async () => {
    expect(await collect(["data:one\ndata:  two\ndata\n\n"])).toEqual(["one\n two\n"]);
  });

  it("strips a leading byte order mark", async () => {
    expect(await collect(["\uFEFFdata: x\n\n"])).toEqual(["x"]);
  });

  it("drops an event the stream ended before terminating", async () => {
    expect(await collect(["data: complete\n\ndata: cut off"])).toEqual(["complete"]);
  });

  it("stops and cancels the body when the signal aborts", async () => {
    let cancelled = false;
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encoder.encode("data: first\n\n"));
      },
      cancel() {
        cancelled = true;
      },
    });
    const controller = new AbortController();
    const seen: string[] = [];
    const read = (async () => {
      for await (const data of readSseData(body, controller.signal)) {
        seen.push(data);
        controller.abort();
      }
    })();
    await expect(read).rejects.toMatchObject({ name: "AbortError" });
    expect(seen).toEqual(["first"]);
    expect(cancelled).toBe(true);
  });

  it("cancels the body when the consumer stops early", async () => {
    let cancelled = false;
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encoder.encode("data: a\n\ndata: b\n\n"));
      },
      cancel() {
        cancelled = true;
      },
    });
    for await (const data of readSseData(body)) {
      expect(data).toBe("a");
      break;
    }
    expect(cancelled).toBe(true);
  });
});

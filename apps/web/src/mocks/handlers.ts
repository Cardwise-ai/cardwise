import {
  type DefaultBodyType,
  http,
  HttpResponse,
  type HttpResponseResolver,
  type PathParams,
} from "msw";
import type { Message } from "@/lib/api/client";
import { MOCK_ACCESS_TOKEN } from "@/lib/auth/shared";
import { apiUrl } from "@/lib/env";
import type { StreamEvent } from "@/lib/stream/events";
import { db, mockCards, pickAnswer } from "./db";

/** Milliseconds between streamed chunks. Tests set it to 0. */
export const mockTiming = { chunkDelayMs: 28 };

const url = (path: string) => `${apiUrl}${path}`;

function requestId(): string {
  return `req_${crypto.randomUUID().slice(0, 8)}`;
}

function errorBody(status: number, code: string, message: string, headers?: HeadersInit): Response {
  return HttpResponse.json(
    { error: { code, message, request_id: requestId() } },
    { status, ...(headers ? { headers } : {}) },
  );
}

function authorized(request: Request): boolean {
  return request.headers.get("authorization") === `Bearer ${MOCK_ACCESS_TOKEN}`;
}

/** Rejects requests without the mock bearer token, like the real API's JWT check. */
function withAuth<P extends PathParams<keyof P>>(
  resolver: HttpResponseResolver<P, DefaultBodyType, undefined>,
): HttpResponseResolver<P, DefaultBodyType, undefined> {
  return (info) => {
    if (!authorized(info.request)) return errorBody(401, "unauthorized", "Sign in to continue.");
    return resolver(info);
  };
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** Splits answer text into model-sized pieces, so card references often straddle two events. */
function textPieces(text: string): string[] {
  const pieces: string[] = [];
  let index = 0;
  while (index < text.length) {
    const size = 6 + ((index * 7) % 13);
    pieces.push(text.slice(index, index + size));
    index += size;
  }
  return pieces;
}

/**
 * Encodes events as SSE and cuts the bytes at uneven offsets, so the browser parser sees events
 * split across network chunks the way a real proxy delivers them.
 */
function streamResponse(
  produce: (
    emit: (event: StreamEvent | ":heartbeat") => Promise<void>,
    signal: AbortSignal,
  ) => Promise<void>,
  onCancel: () => void,
): Response {
  const encoder = new TextEncoder();
  const abort = new AbortController();
  const body = new ReadableStream<Uint8Array>({
    async start(controller) {
      let cut = 0;
      const emit = async (event: StreamEvent | ":heartbeat") => {
        if (abort.signal.aborted) throw abort.signal.reason;
        const frame =
          event === ":heartbeat" ? ": heartbeat\n\n" : `data: ${JSON.stringify(event)}\n\n`;
        const bytes = encoder.encode(frame);
        let offset = 0;
        while (offset < bytes.length) {
          cut = (cut + 17) % 41;
          const end = Math.min(bytes.length, offset + 9 + cut);
          controller.enqueue(bytes.slice(offset, end));
          offset = end;
        }
        if (mockTiming.chunkDelayMs > 0) await sleep(mockTiming.chunkDelayMs);
      };
      try {
        await produce(emit, abort.signal);
        controller.close();
      } catch {
        // Cancelled by the client.
      }
    },
    cancel() {
      abort.abort();
      onCancel();
    },
  });
  return new Response(body, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-store",
      "X-Accel-Buffering": "no",
    },
  });
}

export const handlers = [
  http.get(url("/healthz"), () => HttpResponse.json({ status: "ok" })),

  http.get(
    url("/v1/chats"),
    withAuth(() => HttpResponse.json({ items: db.listChats(), next_cursor: null })),
  ),

  http.post(
    url("/v1/chats"),
    withAuth(async ({ request }) => {
      const body = (await request.json().catch(() => ({}))) as { title?: string | null };
      if (body.title && body.title.length > 120) {
        return errorBody(422, "bad_request", "Titles can be up to 120 characters.");
      }
      return HttpResponse.json(db.createChat(body.title), { status: 201 });
    }),
  ),

  http.patch<{ chatId: string }>(
    url("/v1/chats/:chatId"),
    withAuth(async ({ request, params }) => {
      const body = (await request.json().catch(() => ({}))) as { title?: string };
      const title = body.title?.trim();
      if (!title || title.length > 120) {
        return errorBody(422, "bad_request", "Titles need 1 to 120 characters.");
      }
      const chat = db.renameChat(params.chatId, title);
      return chat ? HttpResponse.json(chat) : errorBody(404, "not_found", "Chat not found.");
    }),
  ),

  http.delete<{ chatId: string }>(
    url("/v1/chats/:chatId"),
    withAuth(({ params }) =>
      db.deleteChat(params.chatId)
        ? new HttpResponse(null, { status: 204 })
        : errorBody(404, "not_found", "Chat not found."),
    ),
  ),

  http.get<{ chatId: string }>(
    url("/v1/chats/:chatId/messages"),
    withAuth(({ params }) => {
      const chat = db.getChat(params.chatId);
      if (!chat) return errorBody(404, "not_found", "Chat not found.");
      return HttpResponse.json({ items: chat.messages, next_cursor: null });
    }),
  ),

  http.post<{ chatId: string }>(
    url("/v1/chats/:chatId/messages"),
    withAuth(async ({ request, params }) => {
      const chat = db.getChat(params.chatId);
      if (!chat) return errorBody(404, "not_found", "Chat not found.");
      const body = (await request.json().catch(() => ({}))) as { content?: unknown };
      const content = typeof body.content === "string" ? body.content.trim() : "";
      if (!content || content.length > 4000) {
        return errorBody(422, "bad_request", "Messages need 1 to 4,000 characters.");
      }
      // Keywords that exercise the error paths in development.
      if (/rate limit/i.test(content)) {
        return errorBody(429, "rate_limited", "Too many messages this hour.", {
          "Retry-After": "1260",
        });
      }

      db.addMessage(chat.id, {
        id: crypto.randomUUID(),
        role: "user",
        content,
        cards: [],
        status: "complete",
        created_at: new Date().toISOString(),
      });

      const reply = pickAnswer(content);
      const failMidway = /model error/i.test(content);
      const assistant: Message = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: "",
        cards: [],
        status: "complete",
        created_at: new Date().toISOString(),
      };
      let saved = false;
      const save = (status: Message["status"]) => {
        if (saved) return;
        saved = true;
        db.addMessage(chat.id, { ...assistant, status });
      };

      return streamResponse(
        async (emit) => {
          await emit({ type: "start", message_id: assistant.id });
          await emit({ type: "tool", name: "search_cards", status: "running" });
          await emit(":heartbeat");
          await sleep(mockTiming.chunkDelayMs * 12);
          await emit({ type: "tool", name: "search_cards", status: "done" });
          const pieces = textPieces(reply.text);
          for (const [index, text] of pieces.entries()) {
            if (failMidway && index === Math.floor(pieces.length / 3)) {
              save("failed");
              await emit({ type: "error", code: "model_unavailable", request_id: requestId() });
              return;
            }
            assistant.content += text;
            await emit({ type: "text", text });
          }
          assistant.cards = reply.cards;
          await emit({ type: "cards", cards: reply.cards });
          save("complete");
          await emit({
            type: "done",
            message_id: assistant.id,
            usage: { input_tokens: 1840, output_tokens: Math.ceil(reply.text.length / 4) },
          });
        },
        () => save("interrupted"),
      );
    }),
  ),

  http.get(
    url("/v1/cards/search"),
    withAuth(({ request }) => {
      const q = new URL(request.url).searchParams.get("q")?.trim().toLowerCase() ?? "";
      if (!q) return errorBody(422, "bad_request", "Enter a search.");
      const items = mockCards
        .filter((card) => card.name.toLowerCase().includes(q))
        .slice(0, 20)
        .map(({ oracle_id, name, mana_cost, type_line, image_uri }) => ({
          oracle_id,
          name,
          mana_cost,
          type_line,
          image_uri,
        }));
      return HttpResponse.json({ items });
    }),
  ),

  http.get<{ oracleId: string }>(
    url("/v1/cards/:oracleId"),
    withAuth(async ({ params }) => {
      if (mockTiming.chunkDelayMs > 0) await sleep(250);
      const card = db.getCard(params.oracleId);
      return card ? HttpResponse.json(card) : errorBody(404, "not_found", "Card not found.");
    }),
  ),
];

import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { MOCK_ACCESS_TOKEN } from "@/lib/auth/shared";
import { apiUrl } from "@/lib/env";
import type { StreamEvent } from "@/lib/stream/events";
import { SEEDED_CHAT_ID } from "@/mocks/db";
import { server } from "@/mocks/node";
import { ApiError, createApiClient } from "./client";
import {
  createChat,
  deleteChat,
  getCard,
  getChat,
  listChats,
  listMessages,
  searchCards,
  sendMessage,
} from "./endpoints";

const api = (token: string | null = MOCK_ACCESS_TOKEN) =>
  createApiClient({ baseUrl: apiUrl, getAccessToken: async () => token });

async function collect(events: AsyncIterable<StreamEvent>): Promise<StreamEvent[]> {
  const out: StreamEvent[] = [];
  for await (const event of events) out.push(event);
  return out;
}

describe("API client", () => {
  it("sends the access token as a bearer header", async () => {
    let auth: string | null = null;
    server.use(
      http.get(`${apiUrl}/v1/chats`, ({ request }) => {
        auth = request.headers.get("authorization");
        return HttpResponse.json({ items: [], next_cursor: null });
      }),
    );
    await listChats(api("token-123"));
    expect(auth).toBe("Bearer token-123");
  });

  it("maps error responses to ApiError", async () => {
    await expect(listChats(api(null))).rejects.toMatchObject({
      name: "ApiError",
      status: 401,
      code: "unauthorized",
    });
  });

  it("reads Retry-After on 429", async () => {
    server.use(
      http.get(`${apiUrl}/v1/chats`, () =>
        HttpResponse.json(
          { error: { code: "rate_limited", message: "Slow down.", request_id: "req_9" } },
          { status: 429, headers: { "Retry-After": "120" } },
        ),
      ),
    );
    const error = await listChats(api()).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      code: "rate_limited",
      retryAfter: 120,
      requestId: "req_9",
      message: "Slow down.",
    });
  });

  it("falls back to a code from the status when the body is not JSON", async () => {
    server.use(
      http.delete(`${apiUrl}/v1/chats/:id`, () => new HttpResponse("gone", { status: 404 })),
    );
    await expect(deleteChat(api(), SEEDED_CHAT_ID)).rejects.toMatchObject({
      status: 404,
      code: "not_found",
    });
  });

  it("reports network failures as code network", async () => {
    server.use(http.get(`${apiUrl}/v1/chats`, () => HttpResponse.error()));
    await expect(listChats(api())).rejects.toMatchObject({ code: "network", status: 0 });
  });

  it("creates a chat and lists its messages", async () => {
    const chat = await createChat(api());
    expect(chat.title).toBe("New chat");
    expect(await listMessages(api(), chat.id)).toEqual([]);
  });

  it("gets one chat, and 404s for one that isn't there", async () => {
    expect(await getChat(api(), SEEDED_CHAT_ID)).toMatchObject({ id: SEEDED_CHAT_ID });
    await expect(getChat(api(), "00000000-0000-4000-8000-000000000000")).rejects.toMatchObject({
      code: "not_found",
    });
  });

  it("searches cards by name", async () => {
    let query: string | null = null;
    server.use(
      http.get(`${apiUrl}/v1/cards/search`, ({ request }) => {
        query = new URL(request.url).searchParams.get("q");
        return HttpResponse.json({
          items: [
            {
              oracle_id: "8d0aa2e2-8b80-4a46-a7a3-4b84de9f0c5f",
              name: "Viscera Seer",
              mana_cost: "{B}",
              type_line: "Creature — Vampire Wizard",
              image_uri: null,
            },
          ],
        });
      }),
    );
    const items = await searchCards(api(), "viscera seer");
    expect(query).toBe("viscera seer");
    expect(items.map((c) => c.name)).toEqual(["Viscera Seer"]);
  });

  it("reports a feature the server hasn't switched on as not_implemented", async () => {
    server.use(
      http.get(`${apiUrl}/v1/cards/:id`, () =>
        HttpResponse.json(
          { error: { code: "not_implemented", message: "Not available yet.", request_id: "r" } },
          { status: 501 },
        ),
      ),
    );
    await expect(getCard(api(), SEEDED_CHAT_ID)).rejects.toMatchObject({
      status: 501,
      code: "not_implemented",
    });
  });
});

describe("expired sessions", () => {
  function client(options: { refreshed: string | null }) {
    const onUnauthorized = vi.fn();
    const refreshAccessToken = vi.fn(async () => options.refreshed);
    const instance = createApiClient({
      baseUrl: apiUrl,
      getAccessToken: async () => "stale-token",
      refreshAccessToken,
      onUnauthorized,
    });
    return { instance, onUnauthorized, refreshAccessToken };
  }

  it("refreshes the token once and repeats the request, body included", async () => {
    const { instance, onUnauthorized, refreshAccessToken } = client({
      refreshed: MOCK_ACCESS_TOKEN,
    });
    const chat = await createChat(instance, "Ramp for Esika");
    expect(chat.title).toBe("Ramp for Esika");
    expect(refreshAccessToken).toHaveBeenCalledOnce();
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it("ends the session when the refreshed token is refused too", async () => {
    const { instance, onUnauthorized, refreshAccessToken } = client({ refreshed: "also-bad" });
    await expect(listChats(instance)).rejects.toMatchObject({ code: "unauthorized" });
    expect(refreshAccessToken).toHaveBeenCalledOnce();
    expect(onUnauthorized).toHaveBeenCalledOnce();
  });

  it("ends the session when there is nothing to refresh", async () => {
    const { instance, onUnauthorized } = client({ refreshed: null });
    const error = await collect(sendMessage(instance, SEEDED_CHAT_ID, "Ramp?")).catch(
      (e: unknown) => e,
    );
    expect(error).toMatchObject({ status: 401, code: "unauthorized" });
    expect(onUnauthorized).toHaveBeenCalledOnce();
  });

  it("leaves other errors alone", async () => {
    const onUnauthorized = vi.fn();
    const refreshAccessToken = vi.fn(async () => MOCK_ACCESS_TOKEN);
    const instance = createApiClient({
      baseUrl: apiUrl,
      getAccessToken: async () => MOCK_ACCESS_TOKEN,
      refreshAccessToken,
      onUnauthorized,
    });
    await expect(getChat(instance, "00000000-0000-4000-8000-000000000000")).rejects.toMatchObject({
      code: "not_found",
    });
    expect(refreshAccessToken).not.toHaveBeenCalled();
    expect(onUnauthorized).not.toHaveBeenCalled();
  });
});

describe("sendMessage", () => {
  it("streams the answer events in order", async () => {
    const events = await collect(sendMessage(api(), SEEDED_CHAT_ID, "Good ramp for Esika?"));
    const types = events.map((e) => e.type);
    expect(types[0]).toBe("start");
    expect(types.at(-1)).toBe("done");
    expect(types).toContain("cards");
    const text = events.flatMap((e) => (e.type === "text" ? [e.text] : [])).join("");
    expect(text).toMatch(/\[\[[0-9a-f-]{36}\|Esika, God of the Tree \/\/ The Prismatic Bridge\]\]/);

    const messages = await listMessages(api(), SEEDED_CHAT_ID);
    expect(messages.at(-1)).toMatchObject({ role: "assistant", status: "complete" });
  });

  it("throws before streaming when the API refuses the message", async () => {
    const error = await collect(sendMessage(api(), SEEDED_CHAT_ID, "hit the rate limit")).catch(
      (e: unknown) => e,
    );
    expect(error).toMatchObject({ status: 429, code: "rate_limited", retryAfter: 1260 });
  });

  it("delivers a mid-stream error event", async () => {
    const events = await collect(sendMessage(api(), SEEDED_CHAT_ID, "trigger a model error"));
    expect(events.at(-1)).toMatchObject({ type: "error", code: "model_unavailable" });
  });

  it("stops when aborted", async () => {
    const controller = new AbortController();
    const seen: string[] = [];
    const run = (async () => {
      for await (const event of sendMessage(api(), SEEDED_CHAT_ID, "Finishers for Selvala", {
        signal: controller.signal,
      })) {
        seen.push(event.type);
        if (event.type === "text") controller.abort();
      }
    })();
    await expect(run).rejects.toMatchObject({ name: "AbortError" });
    expect(seen).not.toContain("done");
  });
});

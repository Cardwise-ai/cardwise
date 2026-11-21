import { readStreamEvents } from "@/lib/stream/read-events";
import type { StreamEvent } from "@/lib/stream/events";
import {
  type ApiClient,
  ApiError,
  type CardDetail,
  type Chat,
  type Message,
  toApiError,
  unwrap,
} from "./client";

export async function listChats(
  api: ApiClient,
  cursor?: string,
): Promise<{ items: Chat[]; nextCursor: string | null }> {
  const page = await unwrap(
    api.GET("/v1/chats", { params: { query: { limit: 50, ...(cursor ? { cursor } : {}) } } }),
  );
  return { items: page.items, nextCursor: page.next_cursor };
}

export function createChat(api: ApiClient, title?: string): Promise<Chat> {
  return unwrap(api.POST("/v1/chats", { body: title ? { title } : {} }));
}

export function renameChat(api: ApiClient, chatId: string, title: string): Promise<Chat> {
  return unwrap(
    api.PATCH("/v1/chats/{chat_id}", { params: { path: { chat_id: chatId } }, body: { title } }),
  );
}

export async function deleteChat(api: ApiClient, chatId: string): Promise<void> {
  await unwrap(api.DELETE("/v1/chats/{chat_id}", { params: { path: { chat_id: chatId } } }));
}

export async function listMessages(api: ApiClient, chatId: string): Promise<Message[]> {
  const page = await unwrap(
    api.GET("/v1/chats/{chat_id}/messages", {
      params: { path: { chat_id: chatId }, query: { limit: 100 } },
    }),
  );
  return page.items;
}

export function getCard(
  api: ApiClient,
  oracleId: string,
  signal?: AbortSignal,
): Promise<CardDetail> {
  return unwrap(
    api.GET("/v1/cards/{oracle_id}", {
      params: { path: { oracle_id: oracleId } },
      ...(signal ? { signal } : {}),
    }),
  );
}

export interface SendMessageOptions {
  signal?: AbortSignal;
  onSkipped?: (reason: string) => void;
}

/**
 * Sends a message and yields the validated answer events as they arrive.
 * Throws ApiError when the request is refused before streaming starts (401, 404, 429...).
 */
export async function* sendMessage(
  api: ApiClient,
  chatId: string,
  content: string,
  options: SendMessageOptions = {},
): AsyncGenerator<StreamEvent, void, undefined> {
  let result;
  try {
    result = await api.POST("/v1/chats/{chat_id}/messages", {
      params: { path: { chat_id: chatId } },
      body: { content },
      headers: { Accept: "text/event-stream" },
      parseAs: "stream",
      ...(options.signal ? { signal: options.signal } : {}),
    });
  } catch (error) {
    if (options.signal?.aborted) throw error;
    throw new ApiError({ status: 0, code: "network", message: "Can't reach Cardwise." });
  }
  const { response } = result;
  if (!response.ok) throw toApiError(response, result.error);
  if (!result.data) {
    throw new ApiError({
      status: response.status,
      code: "internal",
      message: "The answer stream was empty.",
    });
  }
  yield* readStreamEvents(result.data, options);
}

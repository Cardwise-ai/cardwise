import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { createApiClient } from "@/lib/api/client";
import { MOCK_ACCESS_TOKEN } from "@/lib/auth/shared";
import { apiUrl } from "@/lib/env";
import { db, SEEDED_CHAT_ID } from "@/mocks/db";
import { mockTiming } from "@/mocks/handlers";
import { useChat } from "./use-chat";

vi.mock("@/lib/api/browser", () => {
  const client = createApiClient({
    baseUrl: apiUrl,
    getAccessToken: async () => MOCK_ACCESS_TOKEN,
  });
  return { getApiClient: () => client };
});

async function readyChat(chatId = SEEDED_CHAT_ID) {
  const hook = renderHook(() => useChat(chatId));
  await waitFor(() => expect(hook.result.current.history.status).toBe("ready"));
  return hook;
}

describe("useChat", () => {
  it("loads the chat history", async () => {
    const { result } = await readyChat();
    expect(result.current.messages.map((m) => m.role)).toEqual(["user", "assistant"]);
    expect(result.current.messages[1]?.cards.length).toBeGreaterThan(0);
  });

  it("reports a chat that does not exist", async () => {
    const { result } = renderHook(() => useChat("00000000-0000-4000-8000-000000000000"));
    await waitFor(() =>
      expect(result.current.history).toMatchObject({ status: "error", notFound: true }),
    );
  });

  it("streams an answer into a new assistant message", async () => {
    const onSettled = vi.fn();
    const { result } = renderHook(() => useChat(SEEDED_CHAT_ID, { onSettled }));
    await waitFor(() => expect(result.current.history.status).toBe("ready"));

    await act(() => result.current.send("Good ramp for Esika?"));

    const answer = result.current.messages.at(-1)!;
    expect(answer).toMatchObject({ role: "assistant", status: "complete", tool: null });
    expect(answer.id).toMatch(/^[0-9a-f-]{36}$/);
    expect(answer.content).toContain("|Esika, God of the Tree // The Prismatic Bridge]]");
    expect(answer.cards.map((c) => c.name)).toContain("Selvala, Heart of the Wilds");
    expect(result.current.messages.at(-2)).toMatchObject({
      role: "user",
      content: "Good ramp for Esika?",
    });
    expect(result.current.streaming).toBe(false);
    expect(onSettled).toHaveBeenCalledOnce();
  });

  it("gives the text back when the message is refused before streaming", async () => {
    const { result } = await readyChat();
    const before = result.current.messages.length;
    await act(() => result.current.send("this will hit the rate limit"));
    expect(result.current.messages).toHaveLength(before);
    expect(result.current.sendError).toMatchObject({ content: "this will hit the rate limit" });
    expect(result.current.sendError?.message).toMatch(/^Too many messages this hour/);
  });

  it("marks the answer failed on a stream error event", async () => {
    const { result } = await readyChat();
    await act(() => result.current.send("cause a model error please"));
    expect(result.current.messages.at(-1)).toMatchObject({
      status: "failed",
      errorCode: "model_unavailable",
    });
  });

  it("keeps what arrived and marks the answer failed when the stream is cut off", async () => {
    const { result } = await readyChat();
    await act(() => result.current.send("Ramp for Esika, then drop the connection"));
    const answer = result.current.messages.at(-1)!;
    expect(answer).toMatchObject({ status: "failed", errorCode: "network" });
    expect(answer.content.length).toBeGreaterThan(0);
  });

  it.each([
    ["is answering in another tab", /still answering another message/],
    ["is not configured yet", /^Answers aren't switched on/],
  ])("explains a refused message that %s", async (content, message) => {
    const { result } = await readyChat();
    await act(() => result.current.send(content));
    expect(result.current.sendError?.message).toMatch(message);
  });

  it("keeps the partial answer as interrupted when stopped", async () => {
    mockTiming.chunkDelayMs = 5;
    try {
      const { result } = await readyChat();
      let sending!: Promise<void>;
      act(() => {
        sending = result.current.send("Finishers for Selvala");
      });
      await waitFor(() =>
        expect(result.current.messages.at(-1)?.content.length).toBeGreaterThan(0),
      );
      act(() => result.current.stop());
      await act(() => sending);
      const answer = result.current.messages.at(-1)!;
      expect(answer.status).toBe("interrupted");
      expect(answer.content.length).toBeGreaterThan(0);
      await waitFor(() =>
        expect(db.getChat(SEEDED_CHAT_ID)?.messages.at(-1)?.status).toBe("interrupted"),
      );
    } finally {
      mockTiming.chunkDelayMs = 0;
    }
  });

  describe("reopened while the API was still answering", () => {
    function askedAgo(ms: number) {
      const chat = db.createChat("Left mid-answer");
      db.addMessage(chat.id, {
        id: crypto.randomUUID(),
        role: "user",
        content: "Finishers for Selvala",
        cards: [],
        status: "complete",
        created_at: new Date(Date.now() - ms).toISOString(),
      });
      return chat.id;
    }

    it("waits for the answer and shows it once saved", async () => {
      const chatId = askedAgo(2_000);
      const { result } = renderHook(() => useChat(chatId, { answerPollMs: 20 }));
      await waitFor(() =>
        expect(result.current.messages.at(-1)).toMatchObject({
          role: "assistant",
          status: "pending",
        }),
      );

      const answerId = crypto.randomUUID();
      db.addMessage(chatId, {
        id: answerId,
        role: "assistant",
        content: "Craterhoof Behemoth.",
        cards: [],
        status: "complete",
        created_at: new Date().toISOString(),
      });
      await waitFor(() =>
        expect(result.current.messages.at(-1)).toMatchObject({ id: answerId, status: "complete" }),
      );
    });

    it("offers to ask again when the answer never arrived", async () => {
      const chatId = askedAgo(30 * 60_000);
      const { result } = await readyChat(chatId);
      const missing = result.current.messages.at(-1)!;
      expect(missing).toMatchObject({ role: "assistant", status: "failed", errorCode: "network" });

      await act(async () => {
        result.current.retry(missing.id);
        await waitFor(() => expect(result.current.streaming).toBe(false));
      });
      expect(result.current.messages.at(-1)).toMatchObject({
        role: "assistant",
        status: "complete",
      });
    });
  });

  it("retries the question behind a failed answer", async () => {
    const { result } = await readyChat();
    await act(() => result.current.send("model error on finishers"));
    const failed = result.current.messages.at(-1)!;
    expect(failed.status).toBe("failed");
    await act(async () => {
      result.current.retry(failed.id);
      await waitFor(() => expect(result.current.streaming).toBe(false));
    });
    const users = result.current.messages.filter((m) => m.role === "user");
    expect(users.at(-1)?.content).toBe("model error on finishers");
  });
});

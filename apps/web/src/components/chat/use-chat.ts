"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getApiClient } from "@/lib/api/browser";
import { ApiError, type CardRef, type Message } from "@/lib/api/client";
import { listMessages, sendMessage } from "@/lib/api/endpoints";
import { describeError } from "@/lib/errors";
import type { StreamErrorCode, ToolName } from "@/lib/stream/events";

export type UiMessageStatus = Message["status"] | "streaming" | "pending";

export interface UiMessage {
  id: string;
  role: Message["role"];
  content: string;
  cards: CardRef[];
  status: UiMessageStatus;
  /** The tool the model is running right now, while streaming. */
  tool?: ToolName | null;
  errorCode?: StreamErrorCode | "network" | undefined;
}

export type HistoryState =
  | { status: "loading" }
  | { status: "ready" }
  | { status: "error"; message: string; notFound: boolean };

export interface SendError {
  message: string;
  /** The text that wasn't sent, put back in the composer. */
  content: string;
}

export function fromApi(message: Message): UiMessage {
  return { ...message, cards: [...message.cards] };
}

/** The API streams an answer for up to 300 s and saves it when the stream ends, with margin. */
const ANSWER_WINDOW_MS = 330_000;
const ANSWER_POLL_MS = 3_000;

/**
 * History that ends on a question has no saved answer yet. On Vercel the API keeps answering
 * after the browser leaves and saves when it finishes, so a recent question gets a placeholder
 * that waits for it; an older one gets a failed answer that can be asked again.
 */
function settleHistory(items: Message[], now: number): { messages: UiMessage[]; waiting: boolean } {
  const messages = items.map(fromApi);
  const last = items.at(-1);
  if (last?.role !== "user") return { messages, waiting: false };
  const waiting = now - Date.parse(last.created_at) < ANSWER_WINDOW_MS;
  messages.push({
    id: `pending-${last.id}`,
    role: "assistant",
    content: "",
    cards: [],
    status: waiting ? "pending" : "failed",
    errorCode: waiting ? undefined : "network",
  });
  return { messages, waiting };
}

export function useChat(
  chatId: string,
  options: { onSettled?: () => void; initialMessage?: string; answerPollMs?: number } = {},
) {
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [history, setHistory] = useState<HistoryState>({ status: "loading" });
  const [sendError, setSendError] = useState<SendError | null>(null);
  const [streaming, setStreaming] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const onSettled = useRef(options.onSettled);
  const [historyAttempt, setHistoryAttempt] = useState(0);
  const answerPollMs = options.answerPollMs ?? ANSWER_POLL_MS;

  useEffect(() => {
    onSettled.current = options.onSettled;
  });

  const updateMessage = useCallback((id: string, update: (message: UiMessage) => UiMessage) => {
    setMessages((current) => current.map((m) => (m.id === id ? update(m) : m)));
  }, []);

  const send = useCallback(
    async (raw: string) => {
      const content = raw.trim();
      if (!content || controller.current) return;
      setSendError(null);
      const abort = new AbortController();
      controller.current = abort;
      setStreaming(true);

      const userId = `local-user-${crypto.randomUUID()}`;
      let assistantId = `local-assistant-${crypto.randomUUID()}`;
      setMessages((current) => [
        ...current,
        { id: userId, role: "user", content, cards: [], status: "complete" },
        {
          id: assistantId,
          role: "assistant",
          content: "",
          cards: [],
          status: "streaming",
          tool: null,
        },
      ]);

      let started = false;
      try {
        for await (const event of sendMessage(getApiClient(), chatId, content, {
          signal: abort.signal,
        })) {
          started = true;
          switch (event.type) {
            case "start": {
              const previous = assistantId;
              assistantId = event.message_id;
              updateMessage(previous, (m) => ({ ...m, id: event.message_id }));
              break;
            }
            case "text":
              updateMessage(assistantId, (m) => ({
                ...m,
                content: m.content + event.text,
                tool: null,
              }));
              break;
            case "tool":
              updateMessage(assistantId, (m) => ({
                ...m,
                tool: event.status === "running" ? event.name : null,
              }));
              break;
            case "cards":
              updateMessage(assistantId, (m) => ({ ...m, cards: event.cards }));
              break;
            case "done":
              updateMessage(assistantId, (m) => ({ ...m, status: "complete", tool: null }));
              break;
            case "error":
              updateMessage(assistantId, (m) => ({
                ...m,
                status: "failed",
                tool: null,
                errorCode: event.code,
              }));
              break;
          }
        }
        // A stream that ends without `done` or `error` was cut off.
        updateMessage(assistantId, (m) =>
          m.status === "streaming"
            ? { ...m, status: "failed", tool: null, errorCode: "network" }
            : m,
        );
      } catch (error) {
        if (abort.signal.aborted) {
          updateMessage(assistantId, (m) => ({ ...m, status: "interrupted", tool: null }));
        } else if (error instanceof ApiError && !started) {
          // Refused before any answer: nothing was saved, so give the text back.
          setMessages((current) => current.filter((m) => m.id !== userId && m.id !== assistantId));
          setSendError({ message: describeError(error, "send"), content });
        } else {
          updateMessage(assistantId, (m) => ({
            ...m,
            status: "failed",
            tool: null,
            errorCode: "network",
          }));
        }
      } finally {
        controller.current = null;
        setStreaming(false);
        onSettled.current?.();
      }
    },
    [chatId, updateMessage],
  );

  const stop = useCallback(() => {
    controller.current?.abort();
  }, []);

  /** Sends the question behind a failed or stopped answer again. */
  const retry = useCallback(
    (assistantId: string) => {
      const index = messages.findIndex((m) => m.id === assistantId);
      const question = messages
        .slice(0, index)
        .reverse()
        .find((m) => m.role === "user");
      if (question) void send(question.content);
    },
    [messages, send],
  );

  const initialMessage = useRef(options.initialMessage);
  useEffect(() => {
    let active = true;
    const pendingFirst = initialMessage.current;
    initialMessage.current = undefined;
    if (pendingFirst || controller.current) {
      // A chat created a moment ago from the start screen has no history to load. The second
      // check covers React's development double-mount while that first answer streams.
      setHistory({ status: "ready" });
      if (pendingFirst) void send(pendingFirst);
      return;
    }
    let poll: ReturnType<typeof setTimeout> | undefined;
    const load = (first: boolean) =>
      listMessages(getApiClient(), chatId).then(
        (items) => {
          if (!active) return;
          // A message sent meanwhile owns the list until its stream settles.
          if (controller.current) {
            poll = setTimeout(() => void load(false), answerPollMs);
            return;
          }
          const settled = settleHistory(items, Date.now());
          setMessages(settled.messages);
          setHistory({ status: "ready" });
          if (settled.waiting) poll = setTimeout(() => void load(false), answerPollMs);
          else if (!first) onSettled.current?.();
        },
        (error: unknown) => {
          if (!active) return;
          if (!first) {
            poll = setTimeout(() => void load(false), answerPollMs);
            return;
          }
          setHistory({
            status: "error",
            message: describeError(error),
            notFound: error instanceof ApiError && error.code === "not_found",
          });
        },
      );
    setHistory({ status: "loading" });
    void load(true);
    return () => {
      active = false;
      clearTimeout(poll);
    };
  }, [chatId, historyAttempt, send, answerPollMs]);

  // Abort on a real unmount only. React's development double-mount remounts synchronously, so
  // the deferred check sees the component mounted again and keeps the stream alive.
  const mounted = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      setTimeout(() => {
        if (!mounted.current) controller.current?.abort();
      }, 0);
    };
  }, []);

  return {
    messages,
    history,
    reloadHistory: () => setHistoryAttempt((n) => n + 1),
    streaming,
    send,
    stop,
    retry,
    sendError,
    dismissSendError: () => setSendError(null),
  };
}

"use client";

import Link from "next/link";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useCardPanel } from "@/components/app/card-panel-context";
import { ChatActions } from "@/components/app/chat-actions";
import { ChatHeader } from "@/components/app/chat-header";
import { useChats } from "@/components/app/chats-context";
import { Button } from "@/components/ui/button";
import { ErrorBanner } from "@/components/ui/error-banner";
import { Skeleton } from "@/components/ui/skeleton";
import { getApiClient } from "@/lib/api/browser";
import { getChat } from "@/lib/api/endpoints";
import { Composer } from "./composer";
import { FreeTierNotice } from "./free-tier-notice";
import { MessageItem } from "./message";
import { useChat } from "./use-chat";

const NEAR_BOTTOM = 96;

function HistorySkeleton() {
  return (
    <div className="space-y-8" aria-hidden>
      <Skeleton className="ml-0 h-11 w-3/5" />
      <div className="space-y-2.5">
        <Skeleton className="h-3 w-16" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-11/12" />
        <Skeleton className="h-4 w-4/5" />
      </div>
    </div>
  );
}

/** One chat: history, the streaming answer, and the composer. */
export function ChatView({ chatId }: { chatId: string }) {
  const chats = useChats();
  const { card, openCard } = useCardPanel();
  const [initialMessage] = useState(() => chats.takePendingMessage(chatId));
  const { touch } = chats;
  const onSettled = useCallback(() => touch(chatId), [touch, chatId]);
  const chat = useChat(chatId, { onSettled, ...(initialMessage ? { initialMessage } : {}) });
  const [draft, setDraft] = useState("");
  const scroller = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  const summary = chats.chats.find((c) => c.id === chatId);

  // The list holds the first page only. A chat past it, or opened while the list failed to load,
  // is fetched on its own so the header has its title and actions.
  const { state: listState, include } = chats;
  const fetchedSummary = useRef<string | null>(null);
  useEffect(() => {
    if (listState === "loading" || summary || fetchedSummary.current === chatId) return;
    fetchedSummary.current = chatId;
    getChat(getApiClient(), chatId).then(include, () => {
      // The history request reports a missing chat; nothing to add here.
    });
  }, [listState, summary, chatId, include]);

  const { sendError } = chat;
  const [restored, setRestored] = useState<typeof sendError>(null);
  if (sendError !== restored) {
    setRestored(sendError);
    // Give back text the server refused, unless the reader has typed something new.
    if (sendError && !draft) setDraft(sendError.content);
  }

  useLayoutEffect(() => {
    const element = scroller.current;
    if (element && stick.current) element.scrollTop = element.scrollHeight;
  }, [chat.messages, chat.history.status]);

  useEffect(() => {
    const element = scroller.current;
    if (!element) return;
    const onScroll = () => {
      stick.current = element.scrollHeight - element.scrollTop - element.clientHeight < NEAR_BOTTOM;
    };
    element.addEventListener("scroll", onScroll, { passive: true });
    return () => element.removeEventListener("scroll", onScroll);
  }, []);

  function submit(value: string) {
    stick.current = true;
    setDraft("");
    void chat.send(value);
  }

  const title = summary?.title ?? (chat.history.status === "error" ? "Chat" : "");
  const notFound = chat.history.status === "error" && chat.history.notFound;

  return (
    <>
      {title ? <title>{`${title} | Cardwise`}</title> : null}
      <ChatHeader title={title} actions={summary ? <ChatActions chat={summary} /> : null} />
      <div ref={scroller} className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-[74ch] px-5 pt-8 pb-12 md:px-8">
          {chat.history.status === "loading" ? <HistorySkeleton /> : null}
          {chat.history.status === "error" ? (
            notFound ? (
              <div>
                <p className="font-semibold">This chat no longer exists.</p>
                <p className="mt-1 text-muted">It may have been deleted in another tab.</p>
                <Button asChild variant="primary" className="mt-4">
                  <Link href="/">Start a new chat</Link>
                </Button>
              </div>
            ) : (
              <ErrorBanner
                action={
                  <Button size="sm" onClick={chat.reloadHistory}>
                    Try again
                  </Button>
                }
              >
                <p className="font-semibold">Couldn&apos;t load this chat.</p>
                <p className="text-sm text-muted">{chat.history.message}</p>
              </ErrorBanner>
            )
          ) : null}
          {chat.history.status === "ready" ? (
            <section
              role="log"
              aria-label="Messages"
              aria-relevant="additions"
              className="space-y-8"
            >
              {chat.messages.map((message) => (
                <MessageItem
                  key={message.id}
                  message={message}
                  activeCardId={card?.oracle_id ?? null}
                  onOpenCard={openCard}
                  onRetry={chat.retry}
                  busy={chat.streaming}
                />
              ))}
            </section>
          ) : null}
        </div>
      </div>
      {notFound ? null : (
        <div className="shrink-0 border-t border-rule bg-surface px-4 pt-3 pb-4 md:px-6">
          <div className="mx-auto w-full max-w-[74ch]">
            {sendError ? (
              <ErrorBanner className="mb-2">
                <p>{sendError.message}</p>
              </ErrorBanner>
            ) : (
              <FreeTierNotice className="mb-2" />
            )}
            <Composer
              value={draft}
              onChange={(value) => {
                setDraft(value);
                if (sendError) chat.dismissSendError();
              }}
              onSubmit={submit}
              onStop={chat.stop}
              streaming={chat.streaming}
              disabled={chat.history.status !== "ready"}
              autoFocus
            />
          </div>
        </div>
      )}
    </>
  );
}

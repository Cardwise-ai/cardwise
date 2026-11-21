"use client";

import { RotateCcw } from "lucide-react";
import { memo } from "react";
import type { CardRef } from "@/lib/api/client";
import { describeStreamError } from "@/lib/errors";
import type { ToolName } from "@/lib/stream/events";
import { CardStrip } from "@/components/cards/card-strip";
import { Markdown } from "@/components/markdown";
import { Button } from "@/components/ui/button";
import type { UiMessage } from "./use-chat";

const toolStatus: Record<ToolName, string> = {
  search_cards: "Searching cards…",
  get_card: "Reading card details…",
  get_rulings: "Checking rulings…",
  similar_cards: "Finding similar cards…",
};

function StreamStatus({ message }: { message: UiMessage }) {
  if (message.status !== "streaming") return null;
  const label = message.tool
    ? toolStatus[message.tool]
    : message.content
      ? null
      : "Reading your question…";
  return (
    <div className="mt-2 flex h-6 items-center gap-2 text-sm text-muted">
      <span aria-hidden className="inline-block h-4 w-0.5 bg-accent animate-caret" />
      {label ? <span role="status">{label}</span> : null}
    </div>
  );
}

function Notice({
  message,
  onRetry,
  disabled,
}: {
  message: UiMessage;
  onRetry: () => void;
  disabled: boolean;
}) {
  if (message.status === "interrupted") {
    return (
      <p className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 border-l-2 border-rule pl-3 text-sm text-muted">
        <span>Stopped. The answer above is incomplete.</span>
        <Button
          variant="ghost"
          size="sm"
          className="-ml-2 text-accent"
          onClick={onRetry}
          disabled={disabled}
        >
          <RotateCcw aria-hidden />
          Ask again
        </Button>
      </p>
    );
  }
  if (message.status === "failed") {
    const text =
      message.errorCode && message.errorCode !== "network"
        ? describeStreamError(message.errorCode)
        : "The connection dropped before the answer finished. Try again.";
    return (
      <div
        role="alert"
        className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 border-l-2 border-danger pl-3 text-sm"
      >
        <span>{text}</span>
        <Button
          variant="ghost"
          size="sm"
          className="-ml-2 text-accent"
          onClick={onRetry}
          disabled={disabled}
        >
          <RotateCcw aria-hidden />
          Try again
        </Button>
      </div>
    );
  }
  return null;
}

export interface MessageItemProps {
  message: UiMessage;
  activeCardId: string | null;
  onOpenCard: (card: CardRef) => void;
  onRetry: (assistantId: string) => void;
  busy: boolean;
}

export const MessageItem = memo(function MessageItem({
  message,
  activeCardId,
  onOpenCard,
  onRetry,
  busy,
}: MessageItemProps) {
  if (message.role === "user") {
    return (
      <article aria-label="You said" className="flex flex-col items-start">
        <h3 className="sr-only">You</h3>
        <div className="max-w-full border-l-2 border-accent bg-accent-wash px-4 py-3 whitespace-pre-wrap [overflow-wrap:anywhere]">
          {message.content}
        </div>
      </article>
    );
  }

  const streaming = message.status === "streaming";
  return (
    <article aria-label="Cardwise answered" aria-busy={streaming || undefined}>
      <h3 className="mb-2 font-serif text-lg font-semibold text-accent">Cardwise</h3>
      {message.content ? (
        <Markdown
          text={message.content}
          cards={message.cards}
          onOpenCard={onOpenCard}
          streaming={streaming}
        />
      ) : null}
      <StreamStatus message={message} />
      <CardStrip cards={message.cards} activeId={activeCardId} onOpenCard={onOpenCard} />
      <Notice message={message} onRetry={() => onRetry(message.id)} disabled={busy} />
    </article>
  );
});

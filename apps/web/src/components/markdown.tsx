"use client";

import { type ComponentProps, memo } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import type { CardRef } from "@/lib/api/client";
import {
  CARD_REF_ATTR,
  isUuid,
  prepareAnswerMarkdown,
  remarkCardRefs,
} from "@/lib/markdown/card-refs";

const remarkPlugins = [remarkGfm, remarkCardRefs];

/** Only absolute https links survive. Everything else (javascript:, data:, relative) is dropped. */
export function safeUrl(url: string): string {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" ? parsed.href : "";
  } catch {
    return "";
  }
}

export interface MarkdownProps {
  text: string;
  /** The message's `cards` event. A reference becomes a button only if its ID is listed here. */
  cards: readonly CardRef[];
  onOpenCard: (card: CardRef) => void;
  streaming?: boolean;
}

function Anchor({ href, children }: ComponentProps<"a">) {
  if (!href) return <span>{children}</span>;
  return (
    <a href={href} target="_blank" rel="noopener noreferrer nofollow">
      {children}
    </a>
  );
}

/**
 * Renders model output. No raw HTML (skipHtml, and no rehype-raw), no images, https links only,
 * and card references checked against the cards the server resolved for this message.
 */
export const Markdown = memo(function Markdown({
  text,
  cards,
  onOpenCard,
  streaming = false,
}: MarkdownProps) {
  const byId = new Map(cards.map((card) => [card.oracle_id.toLowerCase(), card]));

  const components: Components = {
    a: Anchor,
    img: () => null,
    span(props) {
      const { children } = props;
      const id = (props as Record<string, unknown>)[CARD_REF_ATTR];
      if (typeof id !== "string") return <span>{children}</span>;
      const card = isUuid(id) ? byId.get(id.toLowerCase()) : undefined;
      if (!card) return <>{children}</>;
      return (
        <button type="button" className="card-ref" onClick={() => onOpenCard(card)}>
          {card.name}
        </button>
      );
    },
  };

  return (
    <div className="prose-answer">
      <ReactMarkdown
        remarkPlugins={remarkPlugins}
        components={components}
        urlTransform={safeUrl}
        skipHtml
      >
        {prepareAnswerMarkdown(text, streaming)}
      </ReactMarkdown>
    </div>
  );
});

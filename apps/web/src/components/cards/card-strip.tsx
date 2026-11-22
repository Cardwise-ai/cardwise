"use client";

import type { CardRef } from "@/lib/api/client";
import { cx } from "@/lib/cx";
import { CardImage } from "./card-image";

/** The cards an answer mentions, as a row of thumbnails that open the card panel. */
export function CardStrip({
  cards,
  activeId,
  onOpenCard,
}: {
  cards: readonly CardRef[];
  activeId: string | null;
  onOpenCard: (card: CardRef) => void;
}) {
  if (!cards.length) return null;
  return (
    <ul
      aria-label="Cards in this answer"
      className="-mx-1 mt-4 flex gap-3 overflow-x-auto px-1 pt-1 pb-3 [scrollbar-width:thin]"
    >
      {cards.map((card) => {
        const active = card.oracle_id === activeId;
        return (
          <li key={card.oracle_id} className="w-[120px] shrink-0">
            <button
              type="button"
              aria-label={`Show ${card.name}`}
              aria-current={active ? "true" : undefined}
              onClick={() => onOpenCard(card)}
              className={cx(
                "block w-full rounded-card transition-transform duration-100 hover:-translate-y-0.5 focus-visible:outline-offset-2",
                active && "outline-2 outline-offset-2 outline-accent",
              )}
            >
              <CardImage uri={card.image_uri} name={card.name} sizes="120px" className="w-full" />
            </button>
          </li>
        );
      })}
    </ul>
  );
}

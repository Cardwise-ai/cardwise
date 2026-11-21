"use client";

import { ExternalLink, X } from "lucide-react";
import { type ReactNode, useCallback, useEffect, useId, useRef, useState } from "react";
import { getApiClient } from "@/lib/api/browser";
import type { CardDetail, CardFace, CardRef, Color } from "@/lib/api/client";
import { getCard } from "@/lib/api/endpoints";
import { cx } from "@/lib/cx";
import { describeError } from "@/lib/errors";
import { Button } from "@/components/ui/button";
import { ErrorBanner } from "@/components/ui/error-banner";
import { IconButton } from "@/components/ui/icon-button";
import { Skeleton } from "@/components/ui/skeleton";
import { CardImage } from "./card-image";
import { ManaCost, ManaSymbol, OracleText } from "./mana";

type DetailState =
  | { status: "loading" }
  | { status: "ready"; card: CardDetail }
  | { status: "error"; message: string };

const cache = new Map<string, CardDetail>();

function useCardDetail(oracleId: string): { state: DetailState; retry: () => void } {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<DetailState & { id: string }>(() => {
    const cached = cache.get(oracleId);
    return cached
      ? { status: "ready", card: cached, id: oracleId }
      : { status: "loading", id: oracleId };
  });

  useEffect(() => {
    const cached = cache.get(oracleId);
    if (cached) return;
    const controller = new AbortController();
    getCard(getApiClient(), oracleId, controller.signal).then(
      (card) => {
        cache.set(oracleId, card);
        setState({ status: "ready", card, id: oracleId });
      },
      (error: unknown) => {
        if (controller.signal.aborted) return;
        setState({ status: "error", message: describeError(error), id: oracleId });
      },
    );
    return () => controller.abort();
  }, [oracleId, attempt]);

  const retry = useCallback(() => {
    setState({ status: "loading", id: oracleId });
    setAttempt((n) => n + 1);
  }, [oracleId]);

  // A different card was opened before its effect ran: show it as loading, or from cache.
  if (state.id !== oracleId) {
    const cached = cache.get(oracleId);
    return { state: cached ? { status: "ready", card: cached } : { status: "loading" }, retry };
  }
  return { state, retry };
}

const colorWords: Record<Color, string> = {
  W: "White",
  U: "Blue",
  B: "Black",
  R: "Red",
  G: "Green",
};

const legalityWords = {
  legal: "Legal",
  not_legal: "Not legal",
  banned: "Banned",
  restricted: "Restricted",
} as const;

function hasFaceImages(card: CardDetail): boolean {
  return card.faces.length > 1 && card.faces.every((face) => face.image_uri);
}

function statLine(
  face: Pick<CardFace, "power" | "toughness" | "loyalty" | "defense">,
): string | null {
  if (face.power != null && face.toughness != null) return `${face.power}/${face.toughness}`;
  if (face.loyalty != null) return `Loyalty ${face.loyalty}`;
  if (face.defense != null) return `Defense ${face.defense}`;
  return null;
}

function FaceText({
  name,
  manaCost,
  typeLine,
  oracleText,
  stats,
  headingId,
  level,
}: {
  name: string;
  manaCost: string;
  typeLine: string;
  oracleText: string;
  stats: string | null;
  headingId?: string;
  level: "h2" | "h3";
}) {
  const Heading = level;
  return (
    <div>
      <div className="flex items-start justify-between gap-3">
        <Heading
          id={headingId}
          tabIndex={headingId ? -1 : undefined}
          className={cx(
            "font-serif font-semibold text-balance focus:outline-none",
            level === "h2" ? "text-xl" : "text-lg",
          )}
        >
          {name}
        </Heading>
        <ManaCost cost={manaCost} className="mt-1 shrink-0" />
      </div>
      <p className="mt-1 font-serif text-base text-muted">{typeLine}</p>
      {oracleText ? (
        <div className="mt-3">
          <OracleText text={oracleText} />
        </div>
      ) : null}
      {stats ? (
        <p className="mt-2 text-right font-serif text-oracle font-semibold">{stats}</p>
      ) : null}
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[120px_1fr] gap-x-3 py-2.5 text-sm">
      <dt className="text-muted">{title}</dt>
      <dd className="min-w-0">{children}</dd>
    </div>
  );
}

function CardFacts({ card }: { card: CardDetail }) {
  const commander = card.legalities.commander;
  return (
    <dl className="mt-5 divide-y divide-rule border-y border-rule">
      <Section title="Color identity">
        {card.color_identity.length ? (
          <span className="flex flex-wrap items-center gap-x-1.5 gap-y-1">
            <span className="inline-flex gap-0.5" aria-hidden>
              {card.color_identity.map((color) => (
                <ManaSymbol key={color} symbol={color} size="sm" />
              ))}
            </span>
            <span>{card.color_identity.map((c) => colorWords[c]).join(", ")}</span>
          </span>
        ) : (
          "Colorless"
        )}
      </Section>
      <Section title="Commander">
        <span className={cx(commander === "banned" && "text-danger")}>
          {commander ? legalityWords[commander] : "Unknown"}
        </span>
      </Section>
      {card.tags.length ? (
        <Section title="Tags">
          <ul className="flex flex-wrap gap-1.5" aria-label="Tags">
            {card.tags.map((tag) => (
              <li
                key={tag.slug}
                className="rounded-control border border-rule bg-surface px-1.5 leading-[22px]"
              >
                {tag.label}
              </li>
            ))}
          </ul>
        </Section>
      ) : null}
    </dl>
  );
}

function Rulings({ card }: { card: CardDetail }) {
  if (!card.rulings.length) return null;
  const dateFormat = new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
  return (
    <details className="group mt-4">
      <summary className="cursor-pointer rounded-control text-sm font-semibold marker:text-muted">
        Rulings ({card.rulings.length})
      </summary>
      <ol className="mt-2 space-y-3">
        {card.rulings.map((ruling, index) => (
          <li key={index} className="text-sm">
            <p>{ruling.text}</p>
            <p className="mt-0.5 text-muted">
              <time dateTime={ruling.published_at}>
                {dateFormat.format(new Date(`${ruling.published_at}T00:00:00`))}
              </time>
            </p>
          </li>
        ))}
      </ol>
    </details>
  );
}

function ScryfallLink({ href }: { href: string }) {
  let safe: string | null = null;
  try {
    const url = new URL(href);
    if (url.protocol === "https:" && url.hostname === "scryfall.com") safe = url.href;
  } catch {
    safe = null;
  }
  if (!safe) return null;
  return (
    <a
      href={safe}
      target="_blank"
      rel="noopener noreferrer"
      className="mt-5 inline-flex items-center gap-1.5 text-sm font-semibold text-accent underline decoration-accent/40 underline-offset-[3px] hover:decoration-accent"
    >
      Open on Scryfall
      <ExternalLink aria-hidden className="size-3.5" />
      <span className="sr-only">(opens in a new tab)</span>
    </a>
  );
}

function CardBody({ card, headingId }: { card: CardDetail; headingId: string }) {
  const [faceIndex, setFaceIndex] = useState(0);
  const flips = hasFaceImages(card);
  const face = flips ? card.faces[faceIndex] : undefined;
  const stacked = !flips && card.faces.length > 1;

  return (
    <>
      <div className="mx-auto w-full max-w-[300px]">
        <CardImage
          uri={face?.image_uri ?? card.image_uri}
          name={face?.name ?? card.name}
          sizes="300px"
          eager
          className="w-full"
        />
        {flips ? (
          <div
            role="group"
            aria-label="Card face"
            className="mt-3 grid grid-cols-2 gap-px border border-rule bg-rule"
          >
            {card.faces.map((f, index) => (
              <button
                key={f.name}
                type="button"
                aria-pressed={index === faceIndex}
                onClick={() => setFaceIndex(index)}
                className="h-8 truncate bg-panel px-2 text-sm text-muted hover:text-ink aria-pressed:bg-accent-wash aria-pressed:font-semibold aria-pressed:text-ink"
              >
                {index === 0 ? "Front" : "Back"}
              </button>
            ))}
          </div>
        ) : null}
      </div>

      <div className="mt-5">
        {face ? (
          <>
            <p id={headingId} tabIndex={-1} className="sr-only">
              {card.name}
            </p>
            <FaceText
              level="h2"
              name={face.name}
              manaCost={face.mana_cost}
              typeLine={face.type_line}
              oracleText={face.oracle_text}
              stats={statLine(face)}
            />
          </>
        ) : stacked ? (
          <>
            <h2
              id={headingId}
              tabIndex={-1}
              className="font-serif text-xl font-semibold focus:outline-none"
            >
              {card.name}
            </h2>
            <div className="mt-3 divide-y divide-rule">
              {card.faces.map((f) => (
                <div key={f.name} className="py-3 first:pt-0">
                  <FaceText
                    level="h3"
                    name={f.name}
                    manaCost={f.mana_cost}
                    typeLine={f.type_line}
                    oracleText={f.oracle_text}
                    stats={statLine(f)}
                  />
                </div>
              ))}
            </div>
          </>
        ) : (
          <FaceText
            level="h2"
            headingId={headingId}
            name={card.name}
            manaCost={card.mana_cost}
            typeLine={card.type_line}
            oracleText={card.oracle_text}
            stats={null}
          />
        )}
      </div>

      <CardFacts card={card} />
      <Rulings card={card} />
      <ScryfallLink href={card.scryfall_uri} />
    </>
  );
}

function CardLoading({ card }: { card: CardRef }) {
  return (
    <div aria-busy="true">
      <div className="mx-auto w-full max-w-[300px]">
        <CardImage uri={card.image_uri} name={card.name} sizes="300px" eager className="w-full" />
      </div>
      <p className="sr-only" role="status">
        Loading {card.name}
      </p>
      <div className="mt-5 space-y-3">
        <Skeleton className="h-6 w-3/5" />
        <Skeleton className="h-4 w-2/5" />
        <Skeleton className="mt-5 h-4 w-full" />
        <Skeleton className="h-4 w-11/12" />
        <Skeleton className="h-4 w-4/5" />
      </div>
    </div>
  );
}

export interface CardPanelProps {
  card: CardRef;
  onClose: () => void;
  /** Docked beside the chat on wide screens; inside a sheet below 1024px. */
  variant: "docked" | "sheet";
}

/** Card details: image, cost, type, oracle text, identity, tags and rulings. */
export function CardPanel({ card, onClose, variant }: CardPanelProps) {
  const headingId = useId();
  const { state, retry } = useCardDetail(card.oracle_id);
  const scroller = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scroller.current?.scrollTo({ top: 0 });
    if (variant === "docked") document.getElementById(headingId)?.focus({ preventScroll: true });
  }, [card.oracle_id, headingId, variant, state.status]);

  return (
    <section
      aria-label={`Card: ${card.name}`}
      className={cx(
        "flex h-full min-h-0 flex-col bg-panel",
        variant === "docked" && "border-l border-rule",
      )}
    >
      <div className="flex h-12 shrink-0 items-center justify-between border-b border-rule pr-2 pl-5">
        <p className="text-sm text-muted">Card details</p>
        {variant === "docked" ? (
          <IconButton label="Close card details" icon={<X aria-hidden />} onClick={onClose} />
        ) : null}
      </div>
      <div ref={scroller} className="min-h-0 flex-1 overflow-y-auto px-5 pt-5 pb-8">
        {state.status === "ready" ? (
          <CardBody key={state.card.oracle_id} card={state.card} headingId={headingId} />
        ) : state.status === "error" ? (
          <ErrorBanner
            action={
              <Button size="sm" onClick={retry}>
                Try again
              </Button>
            }
          >
            <p className="font-semibold">Couldn&apos;t load {card.name}.</p>
            <p className="text-sm text-muted">{state.message}</p>
          </ErrorBanner>
        ) : (
          <CardLoading card={card} />
        )}
      </div>
    </section>
  );
}

"use client";

import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
} from "react";
import { usePathname } from "next/navigation";
import type { CardRef } from "@/lib/api/client";

interface CardPanelContextValue {
  card: CardRef | null;
  openCard: (card: CardRef) => void;
  closeCard: () => void;
}

const CardPanelContext = createContext<CardPanelContextValue | null>(null);

export function useCardPanel(): CardPanelContextValue {
  const value = useContext(CardPanelContext);
  if (!value) throw new Error("useCardPanel must be used inside <CardPanelProvider>");
  return value;
}

export function CardPanelProvider({ children }: { children: ReactNode }) {
  const [card, setCard] = useState<CardRef | null>(null);
  const pathname = usePathname();
  const [cardPath, setCardPath] = useState(pathname);
  // A card belongs to the chat it was opened from.
  if (cardPath !== pathname) {
    setCardPath(pathname);
    setCard(null);
  }
  // Focus returns here when the panel closes, so keyboard users keep their place in the answer.
  const returnFocus = useRef<HTMLElement | null>(null);

  const openCard = useCallback((next: CardRef) => {
    if (document.activeElement instanceof HTMLElement) returnFocus.current = document.activeElement;
    setCard(next);
  }, []);

  const closeCard = useCallback(() => {
    setCard(null);
    const target = returnFocus.current;
    returnFocus.current = null;
    if (target?.isConnected) requestAnimationFrame(() => target.focus());
  }, []);

  const value = useMemo(() => ({ card, openCard, closeCard }), [card, openCard, closeCard]);
  return <CardPanelContext.Provider value={value}>{children}</CardPanelContext.Provider>;
}

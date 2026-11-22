"use client";

import { Info, X } from "lucide-react";
import { useRef, useSyncExternalStore } from "react";
import { IconButton } from "@/components/ui/icon-button";
import { cx } from "@/lib/cx";
import { llmTier, MESSAGES_PER_HOUR } from "@/lib/env";

export const FREE_TIER_NOTICE_KEY = "cardwise.free-tier-notice.dismissed";

const listeners = new Set<() => void>();
// Covers browsers that refuse localStorage, so a dismissal still lasts until the page reloads.
let dismissedHere = false;

function isDismissed(): boolean {
  if (dismissedHere) return true;
  try {
    return window.localStorage.getItem(FREE_TIER_NOTICE_KEY) === "1";
  } catch {
    return false;
  }
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  const onStorage = (event: StorageEvent) => {
    if (event.key === FREE_TIER_NOTICE_KEY || event.key === null) listener();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

function dismiss(): void {
  dismissedHere = true;
  try {
    window.localStorage.setItem(FREE_TIER_NOTICE_KEY, "1");
  } catch {
    // Storage is unavailable; the in-memory flag above still hides the notice.
  }
  for (const listener of listeners) listener();
}

/** Tests only: forget a dismissal made in this page. */
export function resetFreeTierNotice(): void {
  dismissedHere = false;
}

/**
 * A quiet note above the composer that answers come from free model tiers and that messages are
 * limited. Hidden once dismissed; the server render leaves it out to avoid a mismatch.
 */
export function FreeTierNotice({ className }: { className?: string }) {
  const dismissed = useSyncExternalStore(subscribe, isDismissed, () => true);
  const root = useRef<HTMLDivElement>(null);
  if (llmTier !== "free" || dismissed) return null;

  return (
    <div
      ref={root}
      role="note"
      aria-label="About free model tiers"
      className={cx(
        "flex items-start gap-2 rounded-field border border-rule bg-surface py-1 pr-1 pl-3 text-sm text-muted",
        className,
      )}
    >
      <Info aria-hidden className="mt-1.5 size-3.5 shrink-0" />
      <p className="min-w-0 flex-1 py-1">
        Cardwise runs on free model tiers, so answers can be slower or shorter when it&apos;s busy.
        You can send {MESSAGES_PER_HOUR} messages an hour.
      </p>
      <IconButton
        label="Dismiss"
        size="sm"
        icon={<X aria-hidden />}
        onClick={() => {
          // The button is about to disappear; keep focus in the same place, on the composer.
          root.current?.parentElement?.querySelector("textarea")?.focus();
          dismiss();
        }}
      />
    </div>
  );
}

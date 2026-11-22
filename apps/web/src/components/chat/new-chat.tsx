"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { ChatHeader } from "@/components/app/chat-header";
import { useChats } from "@/components/app/chats-context";
import { ErrorBanner } from "@/components/ui/error-banner";
import { describeError } from "@/lib/errors";
import { Composer } from "./composer";
import { FreeTierNotice } from "./free-tier-notice";

const examples = [
  "What are the best free sacrifice outlets for Meren of Clan Nel Toth?",
  "Good ramp creatures for an Abzan deck under four mana",
  "My Selvala deck stalls out. What finishers should I add?",
];

/** The start of a new chat. The chat is created when the first message is sent. */
export function NewChat() {
  const { create, setPendingMessage } = useChats();
  const router = useRouter();
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function start(content: string) {
    const text = content.trim();
    if (!text || busy) return;
    setBusy(true);
    setError(null);
    try {
      const chat = await create();
      setPendingMessage(chat.id, text);
      setDraft("");
      setBusy(false);
      router.push(`/chats/${chat.id}`);
    } catch (e) {
      setError(describeError(e));
      setDraft(text);
      setBusy(false);
    }
  }

  return (
    <>
      <ChatHeader title={<span className="font-normal text-muted">New chat</span>} />
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto flex w-full max-w-[74ch] flex-col px-5 pt-[clamp(56px,13vh,124px)] pb-12 md:px-8">
          <h2 className="max-w-[18ch] text-balance font-serif text-[clamp(2rem,4vw,3rem)] leading-[1.05] font-semibold tracking-[-0.035em]">
            What is your deck trying to do?
          </h2>
          <p className="mt-4 max-w-[56ch] text-muted">
            Name your commander, your colors, or the moment the deck falls apart. Cardwise will find
            candidates and keep their oracle text close at hand.
          </p>
          <h3 className="mt-10 font-serif text-lg font-semibold">Start with a question</h3>
          <ul className="mt-3 max-w-[64ch] divide-y divide-rule border-y border-rule">
            {examples.map((example) => (
              <li key={example}>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void start(example)}
                  className="flex w-full items-start gap-3 px-2 py-3.5 text-left font-serif text-base leading-6 hover:bg-hover focus-visible:outline-offset-[-2px] disabled:text-muted sm:text-lg"
                >
                  <span aria-hidden className="mt-[9px] size-2 shrink-0 rounded-full bg-brass" />
                  <span>{example}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      </div>
      <div className="shrink-0 border-t border-rule bg-surface px-4 pt-3 pb-4 md:px-6">
        <div className="mx-auto w-full max-w-[72ch]">
          {error ? (
            <ErrorBanner className="mb-2">
              <p>{error}</p>
            </ErrorBanner>
          ) : (
            <FreeTierNotice className="mb-2" />
          )}
          <Composer
            value={draft}
            onChange={(value) => {
              setDraft(value);
              setError(null);
            }}
            onSubmit={(value) => void start(value)}
            disabled={busy}
            autoFocus
          />
        </div>
      </div>
    </>
  );
}

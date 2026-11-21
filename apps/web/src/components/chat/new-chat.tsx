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
        <div className="mx-auto flex w-full max-w-[72ch] flex-col px-4 pt-[min(14vh,120px)] pb-10 md:px-6">
          <h2 className="text-xl font-semibold">Ask about cards for your deck</h2>
          <p className="mt-2 max-w-[56ch] text-muted">
            Tell Cardwise your commander and what the deck is missing. Every card it suggests links
            to its oracle text, so you can check the wording before you add it.
          </p>
          <h3 className="mt-8 text-sm text-muted">Try one of these</h3>
          <ul className="mt-2 divide-y divide-rule border-y border-rule">
            {examples.map((example) => (
              <li key={example}>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void start(example)}
                  className="block w-full px-1 py-2.5 text-left hover:bg-hover hover:text-ink focus-visible:outline-offset-[-2px] disabled:text-muted"
                >
                  {example}
                </button>
              </li>
            ))}
          </ul>
        </div>
      </div>
      <div className="shrink-0 px-4 pb-4 md:px-6">
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

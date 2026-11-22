"use client";

import { Plus } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { signOut } from "@/lib/auth/sign-out";
import { cx } from "@/lib/cx";
import { groupChats } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ChatActions } from "./chat-actions";
import { ThemeToggle } from "./theme-toggle";
import { Wordmark } from "./wordmark";
import { useChats } from "./chats-context";

function ChatListBody() {
  const { chats, state, reload } = useChats();
  const pathname = usePathname();

  if (state === "loading") {
    return (
      <div className="space-y-3 px-4 pt-3" aria-hidden>
        <Skeleton className="h-3 w-12" />
        <Skeleton className="h-4 w-44" />
        <Skeleton className="h-4 w-36" />
        <Skeleton className="mt-5 h-3 w-24" />
        <Skeleton className="h-4 w-40" />
      </div>
    );
  }
  if (state === "error") {
    return (
      <div className="px-4 pt-3 text-sm text-rail-ink">
        <p>Couldn&apos;t load your chats.</p>
        <Button
          size="sm"
          className="mt-2 border-rail-rule bg-transparent text-rail-ink hover:bg-rail-hover"
          onClick={reload}
        >
          Try again
        </Button>
      </div>
    );
  }
  if (!chats.length) {
    return <p className="px-4 pt-3 text-sm text-rail-muted">Your chats will show up here.</p>;
  }

  return (
    <>
      {groupChats(chats).map((group) => (
        <section key={group.label} aria-labelledby={`group-${group.label}`} className="mb-4">
          <h2 id={`group-${group.label}`} className="px-4 pb-1 text-sm text-rail-muted">
            {group.label}
          </h2>
          <ul>
            {group.chats.map((chat) => {
              const href = `/chats/${chat.id}`;
              const active = pathname === href;
              return (
                <li
                  key={chat.id}
                  className={cx(
                    "group relative flex items-center border-l-2",
                    active
                      ? "border-brass bg-rail-hover"
                      : "border-transparent hover:bg-rail-hover",
                  )}
                >
                  <Link
                    href={href}
                    aria-current={active ? "page" : undefined}
                    className={cx(
                      "block min-w-0 flex-1 truncate py-1.5 pr-1 pl-3.5 text-rail-ink focus-visible:outline-offset-[-2px]",
                      active ? "font-semibold" : "text-rail-muted",
                    )}
                  >
                    {chat.title}
                  </Link>
                  <ChatActions
                    chat={chat}
                    className={cx(
                      "mr-1.5 text-rail-muted hover:bg-rail-hover hover:text-rail-ink data-[state=open]:bg-rail-hover data-[state=open]:text-rail-ink md:opacity-0 md:group-focus-within:opacity-100 md:group-hover:opacity-100 md:data-[state=open]:opacity-100",
                      active && "md:opacity-100",
                    )}
                  />
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </>
  );
}

/** Chat list: wordmark, new chat, chats grouped by date, and the account footer. */
export function Sidebar({ email }: { email: string }) {
  return (
    <div className="dark-field flex h-full min-h-0 flex-col bg-rail text-rail-ink">
      <div className="flex h-14 shrink-0 items-center px-5">
        <Link href="/" className="rounded-control">
          <Wordmark inverse />
        </Link>
      </div>
      <div className="px-3 pb-5">
        <Button
          asChild
          className="w-full justify-start border border-rail-rule bg-panel text-accent hover:bg-hover"
        >
          <Link href="/">
            <Plus aria-hidden />
            New chat
          </Link>
        </Button>
      </div>
      <nav aria-label="Chats" className="min-h-0 flex-1 overflow-y-auto pb-4">
        <ChatListBody />
      </nav>
      <div className="shrink-0 border-t border-rail-rule p-3">
        <ThemeToggle variant="rail" className="mb-2 w-full justify-start" />
        <div className="flex items-center gap-2 pl-1">
          <p className="min-w-0 flex-1 truncate text-sm text-rail-muted" title={email}>
            {email}
          </p>
          <form action={signOut}>
            <Button
              type="submit"
              variant="ghost"
              size="sm"
              className="text-rail-ink hover:bg-rail-hover hover:text-rail-ink"
            >
              Sign out
            </Button>
          </form>
        </div>
      </div>
    </div>
  );
}

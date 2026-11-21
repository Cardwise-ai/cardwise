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
      <div className="px-4 pt-3 text-sm text-white">
        <p>Couldn&apos;t load your chats.</p>
        <Button
          size="sm"
          className="mt-2 border-white/30 bg-transparent text-white hover:bg-white/10"
          onClick={reload}
        >
          Try again
        </Button>
      </div>
    );
  }
  if (!chats.length) {
    return <p className="px-4 pt-3 text-sm text-white/70">Your chats will show up here.</p>;
  }

  return (
    <>
      {groupChats(chats).map((group) => (
        <section key={group.label} aria-labelledby={`group-${group.label}`} className="mb-4">
          <h2 id={`group-${group.label}`} className="px-4 pb-1 text-sm text-white/65">
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
                    active ? "border-brass bg-white/10" : "border-transparent hover:bg-white/10",
                  )}
                >
                  <Link
                    href={href}
                    aria-current={active ? "page" : undefined}
                    className={cx(
                      "block min-w-0 flex-1 truncate py-1.5 pr-1 pl-3.5 text-white focus-visible:outline-offset-[-2px]",
                      active ? "font-semibold" : "text-white/85",
                    )}
                  >
                    {chat.title}
                  </Link>
                  <ChatActions
                    chat={chat}
                    className={cx(
                      "mr-1.5 text-white/70 hover:bg-white/10 hover:text-white data-[state=open]:bg-white/10 data-[state=open]:text-white md:opacity-0 md:group-focus-within:opacity-100 md:group-hover:opacity-100 md:data-[state=open]:opacity-100",
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
    <div className="dark-field flex h-full min-h-0 flex-col bg-accent text-white">
      <div className="flex h-14 shrink-0 items-center px-5">
        <Link href="/" className="rounded-control">
          <Wordmark inverse />
        </Link>
      </div>
      <div className="px-3 pb-5">
        <Button
          asChild
          className="w-full justify-start border border-white/50 bg-panel text-accent hover:bg-white"
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
      <div className="flex shrink-0 items-center gap-2 border-t border-white/20 py-3 pr-2 pl-4">
        <p className="min-w-0 flex-1 truncate text-sm text-white/70" title={email}>
          {email}
        </p>
        <form action={signOut}>
          <Button
            type="submit"
            variant="ghost"
            size="sm"
            className="text-white hover:bg-white/10 hover:text-white"
          >
            Sign out
          </Button>
        </form>
      </div>
    </div>
  );
}

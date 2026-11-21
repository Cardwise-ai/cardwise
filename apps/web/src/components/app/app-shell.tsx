"use client";

import { usePathname } from "next/navigation";
import { type ReactNode, useMemo, useState } from "react";
import { CardPanel } from "@/components/cards/card-panel";
import { Dialog, SheetContent } from "@/components/ui/dialog";
import { Toaster } from "@/components/ui/toast";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useMediaQuery, WIDE } from "@/lib/use-media-query";
import { CardPanelProvider, useCardPanel } from "./card-panel-context";
import { ChatsProvider } from "./chats-context";
import { ShellProvider } from "./shell-context";
import { Sidebar } from "./sidebar";

function CardPanelSlot() {
  const { card, closeCard } = useCardPanel();
  const wide = useMediaQuery(WIDE);
  if (!card) return null;
  if (wide) {
    return (
      <div className="w-[380px] shrink-0 xl:w-[420px]">
        <CardPanel card={card} onClose={closeCard} variant="docked" />
      </div>
    );
  }
  return (
    <Dialog open onOpenChange={(open) => !open && closeCard()}>
      <SheetContent side="right" title={card.name} closeLabel="Close card details">
        <CardPanel card={card} onClose={closeCard} variant="sheet" />
      </SheetContent>
    </Dialog>
  );
}

/**
 * Three columns on wide screens: chat list, chat, card panel. Below 1024px the card panel is a
 * sheet; below 768px the chat list is a drawer.
 */
export function AppShell({ email, children }: { email: string; children: ReactNode }) {
  const [navOpen, setNavOpen] = useState(false);
  const pathname = usePathname();
  const [navPath, setNavPath] = useState(pathname);
  // Close the drawer after navigating from it.
  if (navPath !== pathname) {
    setNavPath(pathname);
    setNavOpen(false);
  }
  const shell = useMemo(() => ({ openNav: () => setNavOpen(true) }), []);

  return (
    <TooltipProvider delayDuration={400}>
      <Toaster>
        <ChatsProvider>
          <CardPanelProvider>
            <ShellProvider value={shell}>
              <div className="flex h-dvh overflow-hidden">
                <aside className="hidden w-64 shrink-0 border-r border-rule md:block">
                  <Sidebar email={email} />
                </aside>
                <Dialog open={navOpen} onOpenChange={setNavOpen}>
                  <SheetContent side="left" title="Chats" closeLabel="Close chats">
                    <Sidebar email={email} />
                  </SheetContent>
                </Dialog>
                <main className="flex min-w-0 flex-1 flex-col bg-panel">{children}</main>
                <CardPanelSlot />
              </div>
            </ShellProvider>
          </CardPanelProvider>
        </ChatsProvider>
      </Toaster>
    </TooltipProvider>
  );
}

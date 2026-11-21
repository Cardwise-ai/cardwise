"use client";

import { Menu as MenuIcon } from "lucide-react";
import type { ReactNode } from "react";
import { IconButton } from "@/components/ui/icon-button";
import { useShell } from "./shell-context";

/** The bar above the chat column: title on the left, actions on the right. */
export function ChatHeader({ title, actions }: { title: ReactNode; actions?: ReactNode }) {
  const { openNav } = useShell();
  return (
    <header className="flex h-12 shrink-0 items-center gap-1.5 border-b border-rule pr-3 pl-2 md:pl-6">
      <IconButton
        label="Show chats"
        icon={<MenuIcon aria-hidden />}
        onClick={openNav}
        className="md:hidden"
      />
      <h1 className="min-w-0 flex-1 truncate font-semibold">{title}</h1>
      {actions}
    </header>
  );
}

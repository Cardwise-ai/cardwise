"use client";

import { DropdownMenu } from "radix-ui";
import type { ComponentPropsWithRef } from "react";
import { cx } from "@/lib/cx";

export const Menu = DropdownMenu.Root;
export const MenuTrigger = DropdownMenu.Trigger;

export function MenuContent({
  className,
  align = "end",
  sideOffset = 4,
  ...props
}: ComponentPropsWithRef<typeof DropdownMenu.Content>) {
  return (
    <DropdownMenu.Portal>
      <DropdownMenu.Content
        align={align}
        sideOffset={sideOffset}
        className={cx(
          "z-50 min-w-44 rounded-popover border border-rule bg-panel py-1 shadow-float animate-fade-in",
          className,
        )}
        {...props}
      />
    </DropdownMenu.Portal>
  );
}

export function MenuItem({
  className,
  tone = "default",
  ...props
}: ComponentPropsWithRef<typeof DropdownMenu.Item> & { tone?: "default" | "danger" }) {
  return (
    <DropdownMenu.Item
      className={cx(
        "flex h-8 cursor-default items-center gap-2.5 px-3 text-base outline-none select-none data-[disabled]:text-muted data-[highlighted]:bg-hover [&_svg]:size-4 [&_svg]:text-muted",
        tone === "danger" && "text-danger [&_svg]:text-danger data-[highlighted]:bg-danger-wash",
        className,
      )}
      {...props}
    />
  );
}

export function MenuSeparator() {
  return <DropdownMenu.Separator className="my-1 h-px bg-rule" />;
}

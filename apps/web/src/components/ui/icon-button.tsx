"use client";

import type { ComponentPropsWithRef, ReactNode } from "react";
import { cx } from "@/lib/cx";
import { Tooltip } from "./tooltip";

export interface IconButtonProps extends Omit<ComponentPropsWithRef<"button">, "children"> {
  /** Accessible name, also shown as the tooltip. */
  label: string;
  icon: ReactNode;
  tooltip?: boolean;
  size?: "sm" | "md";
}

export function IconButton({
  label,
  icon,
  tooltip = true,
  size = "md",
  className,
  type = "button",
  ...props
}: IconButtonProps) {
  const button = (
    <button
      type={type}
      aria-label={label}
      className={cx(
        "inline-flex shrink-0 items-center justify-center rounded-control text-muted transition-colors duration-100 hover:bg-hover hover:text-ink disabled:cursor-not-allowed disabled:opacity-50 data-[state=open]:bg-hover data-[state=open]:text-ink [&_svg]:size-4",
        size === "sm" ? "size-7" : "size-8",
        className,
      )}
      {...props}
    >
      {icon}
    </button>
  );
  return tooltip ? <Tooltip label={label}>{button}</Tooltip> : button;
}

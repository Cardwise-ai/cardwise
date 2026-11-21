import { Slot } from "radix-ui";
import type { ComponentPropsWithRef } from "react";
import { cx } from "@/lib/cx";

export type ButtonVariant = "primary" | "quiet" | "ghost" | "danger";
export type ButtonSize = "sm" | "md";

const variants: Record<ButtonVariant, string> = {
  primary:
    "bg-accent text-white hover:bg-accent-strong disabled:bg-accent/50 disabled:text-white/90",
  quiet:
    "border border-rule bg-panel text-ink hover:border-rule-strong hover:bg-hover disabled:text-muted",
  ghost: "text-ink hover:bg-hover disabled:text-muted",
  danger: "bg-danger text-white hover:bg-danger-strong disabled:bg-danger/50",
};

const sizes: Record<ButtonSize, string> = {
  sm: "h-8 px-2.5 text-sm gap-1.5",
  md: "h-9 px-3.5 text-base gap-2",
};

export interface ButtonProps extends ComponentPropsWithRef<"button"> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  asChild?: boolean;
}

export function buttonClasses(variant: ButtonVariant = "quiet", size: ButtonSize = "md") {
  return cx(
    "inline-flex shrink-0 items-center justify-center rounded-control font-semibold whitespace-nowrap select-none transition-colors duration-100 disabled:cursor-not-allowed [&_svg]:size-4 [&_svg]:shrink-0",
    variants[variant],
    sizes[size],
  );
}

export function Button({
  variant = "quiet",
  size = "md",
  asChild = false,
  className,
  type,
  ...props
}: ButtonProps) {
  const Component = asChild ? Slot.Root : "button";
  return (
    <Component
      {...(asChild ? {} : { type: type ?? "button" })}
      className={cx(buttonClasses(variant, size), className)}
      {...props}
    />
  );
}

"use client";

import { X } from "lucide-react";
import { Dialog as DialogPrimitive } from "radix-ui";
import type { ComponentPropsWithRef, ReactNode } from "react";
import { cx } from "@/lib/cx";

export const Dialog = DialogPrimitive.Root;
export const DialogTrigger = DialogPrimitive.Trigger;
export const DialogClose = DialogPrimitive.Close;

function Overlay() {
  return <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-ink/30 animate-fade-in" />;
}

export interface DialogContentProps extends ComponentPropsWithRef<typeof DialogPrimitive.Content> {
  title: string;
  description?: ReactNode;
}

/** A centered dialog for confirmations and short forms. */
export function DialogContent({
  title,
  description,
  children,
  className,
  ...props
}: DialogContentProps) {
  return (
    <DialogPrimitive.Portal>
      <Overlay />
      <DialogPrimitive.Content
        className={cx(
          "fixed top-1/2 left-1/2 z-50 w-[calc(100%-32px)] max-w-[420px] -translate-x-1/2 -translate-y-1/2 rounded-popover border border-rule bg-panel p-6 shadow-float animate-fade-in focus:outline-none",
          className,
        )}
        {...(description ? {} : { "aria-describedby": undefined })}
        {...props}
      >
        <DialogPrimitive.Title className="text-lg font-semibold">{title}</DialogPrimitive.Title>
        {description ? (
          <DialogPrimitive.Description className="mt-2 text-muted">
            {description}
          </DialogPrimitive.Description>
        ) : null}
        {children}
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}

export function DialogFooter({ children }: { children: ReactNode }) {
  return <div className="mt-6 flex justify-end gap-2">{children}</div>;
}

export interface SheetContentProps extends ComponentPropsWithRef<typeof DialogPrimitive.Content> {
  side: "left" | "right";
  /** Visually hidden title for screen readers when the sheet has no visible heading. */
  title: string;
  closeLabel?: string;
}

/** A full-height panel that slides in from an edge: the chat drawer and the small-screen card sheet. */
export function SheetContent({
  side,
  title,
  closeLabel = "Close",
  children,
  className,
  ...props
}: SheetContentProps) {
  return (
    <DialogPrimitive.Portal>
      <Overlay />
      <DialogPrimitive.Content
        aria-describedby={undefined}
        className={cx(
          "fixed inset-y-0 z-50 flex flex-col bg-panel shadow-float focus:outline-none",
          side === "left"
            ? "left-0 w-[min(300px,calc(100%-48px))] border-r border-rule animate-sheet-in-left"
            : "right-0 w-[min(440px,100%)] border-l border-rule animate-sheet-in-right",
          className,
        )}
        {...props}
      >
        <DialogPrimitive.Title className="sr-only">{title}</DialogPrimitive.Title>
        <DialogPrimitive.Close
          aria-label={closeLabel}
          className="absolute top-2 right-2 z-10 inline-flex size-8 items-center justify-center rounded-control text-muted hover:bg-hover hover:text-ink [&_svg]:size-4"
        >
          <X aria-hidden />
        </DialogPrimitive.Close>
        {children}
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}

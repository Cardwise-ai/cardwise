"use client";

import { Ellipsis, Pencil, Trash2 } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { type FormEvent, type RefObject, useRef, useState } from "react";
import type { Chat } from "@/lib/api/client";
import { cx } from "@/lib/cx";
import { describeError } from "@/lib/errors";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/input";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@/components/ui/menu";
import { useToast } from "@/components/ui/toast";
import { useChats } from "./chats-context";

interface ChatDialogProps {
  chat: Chat;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  returnFocus: RefObject<HTMLButtonElement | null>;
}

function restoreFocus(returnFocus: ChatDialogProps["returnFocus"]) {
  return (event: Event) => {
    const target = returnFocus.current;
    if (target?.isConnected) {
      event.preventDefault();
      target.focus();
    }
  };
}

function RenameDialog({ chat, open, onOpenChange, returnFocus }: ChatDialogProps) {
  const { rename } = useChats();
  const [title, setTitle] = useState(chat.title);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const next = title.trim();
    if (!next) {
      setError("Enter a title.");
      return;
    }
    setSaving(true);
    try {
      await rename(chat.id, next);
      onOpenChange(false);
    } catch (e) {
      setError(describeError(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (next) {
          setTitle(chat.title);
          setError(null);
        }
        onOpenChange(next);
      }}
    >
      <DialogContent title="Rename chat" onCloseAutoFocus={restoreFocus(returnFocus)}>
        <form onSubmit={onSubmit} className="mt-4" noValidate>
          <Field
            id={`rename-${chat.id}`}
            label="Title"
            hint={error ? <span className="text-danger">{error}</span> : null}
          >
            <Input
              id={`rename-${chat.id}`}
              value={title}
              maxLength={120}
              aria-invalid={error ? true : undefined}
              onChange={(event) => {
                setTitle(event.target.value);
                setError(null);
              }}
              onFocus={(event) => event.target.select()}
            />
          </Field>
          <DialogFooter>
            <DialogClose asChild>
              <Button>Cancel</Button>
            </DialogClose>
            <Button type="submit" variant="primary" disabled={saving}>
              {saving ? "Saving…" : "Save"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function DeleteDialog({ chat, open, onOpenChange, returnFocus }: ChatDialogProps) {
  const { remove } = useChats();
  const toast = useToast();
  const router = useRouter();
  const pathname = usePathname();
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onDelete() {
    setDeleting(true);
    setError(null);
    try {
      await remove(chat.id);
      onOpenChange(false);
      toast({ title: "Chat deleted" });
      if (pathname === `/chats/${chat.id}`) router.push("/");
    } catch (e) {
      setError(describeError(e));
    } finally {
      setDeleting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        title="Delete this chat?"
        onCloseAutoFocus={restoreFocus(returnFocus)}
        description={
          <>
            &ldquo;{chat.title}&rdquo; and all of its messages will be deleted. You can&apos;t undo
            this.
          </>
        }
      >
        {error ? (
          <p role="alert" className="mt-3 text-sm text-danger">
            {error}
          </p>
        ) : null}
        <DialogFooter>
          <DialogClose asChild>
            <Button>Cancel</Button>
          </DialogClose>
          <Button variant="danger" onClick={onDelete} disabled={deleting}>
            {deleting ? "Deleting…" : "Delete chat"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** The ⋯ menu for a chat with its rename and delete dialogs. Used in the chat list and the chat header. */
export function ChatActions({ chat, className }: { chat: Chat; className?: string }) {
  const [dialog, setDialog] = useState<"rename" | "delete" | null>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  return (
    <>
      <Menu modal={false}>
        <MenuTrigger
          ref={trigger}
          aria-label={`Options for ${chat.title}`}
          className={cx(
            "inline-flex size-7 shrink-0 items-center justify-center rounded-control text-muted hover:bg-hover hover:text-ink data-[state=open]:bg-hover data-[state=open]:text-ink [&_svg]:size-4",
            className,
          )}
        >
          <Ellipsis aria-hidden />
        </MenuTrigger>
        <MenuContent>
          <MenuItem onSelect={() => setDialog("rename")}>
            <Pencil aria-hidden />
            Rename
          </MenuItem>
          <MenuItem tone="danger" onSelect={() => setDialog("delete")}>
            <Trash2 aria-hidden />
            Delete chat
          </MenuItem>
        </MenuContent>
      </Menu>
      <RenameDialog
        chat={chat}
        open={dialog === "rename"}
        onOpenChange={(open) => setDialog(open ? "rename" : null)}
        returnFocus={trigger}
      />
      <DeleteDialog
        chat={chat}
        open={dialog === "delete"}
        onOpenChange={(open) => setDialog(open ? "delete" : null)}
        returnFocus={trigger}
      />
    </>
  );
}

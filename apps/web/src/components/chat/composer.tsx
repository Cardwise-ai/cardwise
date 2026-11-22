"use client";

import { Square } from "lucide-react";
import { type FormEvent, type KeyboardEvent, useEffect, useId, useRef } from "react";
import { Button } from "@/components/ui/button";
import { cx } from "@/lib/cx";

export const MAX_MESSAGE_LENGTH = 4000;
const COUNTER_FROM = 3500;
const MAX_HEIGHT = 240;

export interface ComposerProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (value: string) => void;
  onStop?: () => void;
  streaming?: boolean;
  disabled?: boolean;
  autoFocus?: boolean;
  placeholder?: string;
}

export function Composer({
  value,
  onChange,
  onSubmit,
  onStop,
  streaming = false,
  disabled = false,
  autoFocus = false,
  placeholder = "Ask about cards for your deck",
}: ComposerProps) {
  const id = useId();
  const textarea = useRef<HTMLTextAreaElement>(null);
  const canSend = !disabled && !streaming && value.trim().length > 0;

  useEffect(() => {
    const element = textarea.current;
    if (!element) return;
    element.style.height = "auto";
    element.style.height = `${Math.min(element.scrollHeight, MAX_HEIGHT)}px`;
  }, [value]);

  useEffect(() => {
    if (autoFocus) textarea.current?.focus();
  }, [autoFocus]);

  function submit(event?: FormEvent) {
    event?.preventDefault();
    if (canSend) onSubmit(value);
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  }

  const count = value.length;
  return (
    <form onSubmit={submit} className="w-full">
      <div className="rounded-control border border-rule border-l-[3px] border-l-accent bg-panel transition-colors focus-within:border-accent hover:border-rule-strong focus-within:hover:border-accent has-[textarea:focus-visible]:outline-2 has-[textarea:focus-visible]:outline-offset-2 has-[textarea:focus-visible]:outline-accent">
        <label htmlFor={id} className="sr-only">
          Message
        </label>
        <textarea
          ref={textarea}
          id={id}
          value={value}
          rows={1}
          maxLength={MAX_MESSAGE_LENGTH}
          placeholder={placeholder}
          disabled={disabled}
          aria-describedby={`${id}-hint`}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={onKeyDown}
          className="block max-h-[240px] min-h-[56px] w-full resize-none bg-transparent px-4 pt-4 pb-1 text-base placeholder:text-muted focus:outline-none disabled:text-muted"
        />
        <div className="flex items-center justify-between gap-3 px-2 pb-2 pl-3.5">
          <p id={`${id}-hint`} className="truncate text-sm text-muted">
            {count >= COUNTER_FROM ? (
              <span className={cx(count >= MAX_MESSAGE_LENGTH && "text-danger")}>
                {count.toLocaleString()} of {MAX_MESSAGE_LENGTH.toLocaleString()} characters
              </span>
            ) : (
              <span className="max-sm:sr-only">Enter to send, Shift+Enter for a new line</span>
            )}
          </p>
          {streaming ? (
            <Button size="sm" onClick={onStop}>
              <Square aria-hidden className="fill-current !size-3" />
              Stop
            </Button>
          ) : (
            <Button type="submit" variant="primary" size="sm" disabled={!canSend}>
              Send
            </Button>
          )}
        </div>
      </div>
    </form>
  );
}

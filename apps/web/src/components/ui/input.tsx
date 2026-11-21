import type { ComponentPropsWithRef, ReactNode } from "react";
import { cx } from "@/lib/cx";

export const inputClasses =
  "w-full rounded-control border border-rule bg-panel px-3 text-base text-ink placeholder:text-muted hover:border-rule-strong focus-visible:border-accent focus-visible:outline-1 focus-visible:outline-offset-0 disabled:bg-surface disabled:text-muted aria-[invalid=true]:border-danger";

export function Input({ className, ...props }: ComponentPropsWithRef<"input">) {
  return <input className={cx(inputClasses, "h-9", className)} {...props} />;
}

export function TextArea({ className, ...props }: ComponentPropsWithRef<"textarea">) {
  return <textarea className={cx(inputClasses, "resize-none py-2", className)} {...props} />;
}

export function Field({
  id,
  label,
  hint,
  children,
}: {
  id: string;
  label: string;
  hint?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-semibold">
        {label}
      </label>
      {children}
      {hint ? <p className="text-sm text-muted">{hint}</p> : null}
    </div>
  );
}

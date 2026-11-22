import { CircleAlert } from "lucide-react";
import type { ReactNode } from "react";
import { cx } from "@/lib/cx";

/** An inline notice that says what happened and what to do next. */
export function ErrorBanner({
  children,
  action,
  className,
}: {
  children: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      role="alert"
      className={cx(
        "flex items-start gap-3 rounded-field border border-danger/30 bg-danger-wash px-3 py-2.5 text-ink",
        className,
      )}
    >
      <CircleAlert aria-hidden className="mt-1 size-4 shrink-0 text-danger" />
      <div className="min-w-0 flex-1">{children}</div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}

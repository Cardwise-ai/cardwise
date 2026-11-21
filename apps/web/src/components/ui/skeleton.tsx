import { cx } from "@/lib/cx";

/** A static placeholder block. No shimmer: motion only follows user actions. */
export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cx("rounded-control bg-placeholder", className)} />;
}

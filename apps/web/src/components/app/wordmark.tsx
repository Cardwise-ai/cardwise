/** The Cardwise name with its mark: a card outline in the accent green. */
export function Wordmark() {
  return (
    <span className="inline-flex items-center gap-2 font-semibold">
      <svg aria-hidden viewBox="0 0 16 20" className="h-5 w-4 text-accent">
        <rect
          x="0.75"
          y="0.75"
          width="14.5"
          height="18.5"
          rx="1.5"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
        />
        <rect x="3.5" y="3.5" width="9" height="7" fill="currentColor" opacity="0.85" />
        <path d="M3.5 13.5h9M3.5 16h6" stroke="currentColor" strokeWidth="1.25" />
      </svg>
      Cardwise
    </span>
  );
}

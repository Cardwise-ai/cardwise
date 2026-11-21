import { Fragment, type ReactNode } from "react";
import { cx } from "@/lib/cx";

const colorNames: Record<string, string> = {
  W: "white",
  U: "blue",
  B: "black",
  R: "red",
  G: "green",
  C: "colorless",
};

const fills: Record<string, string> = {
  W: "bg-mana-w",
  U: "bg-mana-u",
  B: "bg-mana-b",
  R: "bg-mana-r",
  G: "bg-mana-g",
  C: "bg-mana-c",
};

/** Words a screen reader reads for one symbol, e.g. `{2/W}` becomes "two generic or white". */
export function describeSymbol(symbol: string): string {
  const parts = symbol.split("/");
  const words = parts.map((part) => {
    if (/^\d+$/.test(part)) return `${part} generic`;
    if (part === "P") return "Phyrexian";
    if (part === "T") return "tap";
    if (part === "Q") return "untap";
    if (part === "S") return "snow";
    if (part === "X" || part === "Y" || part === "Z") return part;
    if (part === "E") return "energy";
    return colorNames[part] ?? part;
  });
  if (parts.length === 2 && parts[1] === "P") return `Phyrexian ${words[0]}`;
  return words.join(" or ");
}

const symbolPattern = /\{([^{}]{1,8})\}/g;

export function parseSymbols(cost: string): string[] {
  return [...cost.matchAll(symbolPattern)].map((match) => match[1] ?? "");
}

function symbolFill(symbol: string): string {
  const colors = symbol.split("/").filter((part) => part in fills);
  const first = colors[0];
  if (!first) return "bg-mana-c";
  return fills[first] ?? "bg-mana-c";
}

function symbolGlyph(symbol: string): string {
  if (symbol.endsWith("/P")) return symbol[0] ?? symbol;
  if (symbol.includes("/")) return symbol.replace("/", "");
  return symbol;
}

/** One mana symbol, drawn as a small filled circle with its letter. */
export function ManaSymbol({ symbol, size = "md" }: { symbol: string; size?: "sm" | "md" }) {
  const glyph = symbolGlyph(symbol);
  return (
    <abbr
      title={describeSymbol(symbol)}
      className={cx(
        "inline-flex shrink-0 items-center justify-center rounded-full border border-ink/25 align-[-0.2em] font-sans font-semibold text-ink no-underline",
        symbolFill(symbol),
        size === "sm"
          ? "size-[15px] text-[9px] leading-none"
          : "size-[18px] text-[10px] leading-none",
        glyph.length > 1 && "tracking-[-0.04em]",
      )}
    >
      <span aria-hidden>{glyph}</span>
      <span className="sr-only">{describeSymbol(symbol)}</span>
    </abbr>
  );
}

/** A mana cost such as `{2}{B}{G}`. Split and double-faced costs keep their `//` separator. */
export function ManaCost({
  cost,
  size = "md",
  className,
}: {
  cost: string;
  size?: "sm" | "md";
  className?: string;
}) {
  if (!cost.trim()) return null;
  const halves = cost.split(" // ");
  return (
    <span className={cx("inline-flex flex-wrap items-center gap-0.5", className)}>
      {halves.map((half, index) => (
        <Fragment key={index}>
          {index > 0 ? <span className="px-1 text-muted">{"//"}</span> : null}
          {parseSymbols(half).map((symbol, i) => (
            <ManaSymbol key={i} symbol={symbol} size={size} />
          ))}
        </Fragment>
      ))}
    </span>
  );
}

/**
 * Oracle text with inline mana symbols. Parenthesized reminder text is set in italic, as on
 * printed cards.
 */
export function OracleText({ text }: { text: string }) {
  const paragraphs = text.split("\n").filter((line) => line.trim() !== "");
  return (
    <div className="space-y-2 font-serif text-oracle">
      {paragraphs.map((line, index) => (
        <p key={index}>{renderInline(line)}</p>
      ))}
    </div>
  );
}

function renderInline(line: string): ReactNode[] {
  const out: ReactNode[] = [];
  const pattern = /(\([^()]*\))|\{([^{}]{1,8})\}/g;
  let last = 0;
  let key = 0;
  for (const match of line.matchAll(pattern)) {
    if (match.index > last) out.push(line.slice(last, match.index));
    if (match[1]) {
      out.push(
        <i key={key++} className="text-ink/80">
          ({renderInline(match[1].slice(1, -1))})
        </i>,
      );
    } else if (match[2]) {
      out.push(<ManaSymbol key={key++} symbol={match[2]} size="sm" />);
    }
    last = match.index + match[0].length;
  }
  if (last < line.length) out.push(line.slice(last));
  return out;
}

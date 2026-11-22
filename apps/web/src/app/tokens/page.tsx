import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { ManaCost, OracleText } from "@/components/cards/mana";
import { Button } from "@/components/ui/button";
import { contrastRatio, palette } from "@/lib/contrast";
import { isMocking } from "@/lib/env";

export const metadata: Metadata = { title: "Design tokens" };

const pairs: Array<[keyof typeof palette, keyof typeof palette]> = [
  ["ink", "panel"],
  ["ink", "surface"],
  ["muted", "panel"],
  ["muted", "surface"],
  ["muted", "hover"],
  ["accent", "panel"],
  ["accent", "surface"],
  ["panel", "accent"],
  ["danger", "panel"],
  ["ink", "danger-wash"],
];

const scale = [
  {
    name: "xl",
    sample: "Ask about cards for your deck",
    className: "text-xl font-semibold",
    spec: "22/28",
  },
  { name: "lg", sample: "Delete this chat?", className: "text-lg font-semibold", spec: "18/28" },
  {
    name: "base",
    sample: "Meren wants free, repeatable sacrifice outlets.",
    className: "text-base",
    spec: "15/24",
  },
  { name: "sm", sample: "Previous 7 days", className: "text-sm", spec: "13/20" },
];

/** A reference sheet for the design tokens. Development and mock builds only. */
export default function TokensPage() {
  if (process.env.NODE_ENV === "production" && !isMocking) notFound();
  return (
    <main className="mx-auto max-w-[880px] px-6 py-12">
      <h1 className="text-xl font-semibold">Design tokens</h1>
      <p className="mt-1 text-muted">
        Colors, type and controls from the engineering spec, section 8.2.
      </p>

      <h2 className="mt-10 text-lg font-semibold">Color</h2>
      <ul className="mt-3 grid grid-cols-2 border-t border-l border-rule bg-panel sm:grid-cols-4">
        {Object.entries(palette).map(([name, hex]) => (
          <li key={name} className="border-r border-b border-rule p-3">
            <div className="h-12 border border-rule" style={{ background: hex }} />
            <p className="mt-2 text-sm font-semibold">{name}</p>
            <p className="text-sm text-muted">{hex}</p>
          </li>
        ))}
      </ul>

      <h2 className="mt-10 text-lg font-semibold">Contrast</h2>
      <table className="mt-3 w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-rule text-left">
            <th className="py-2 font-semibold">Text</th>
            <th className="py-2 font-semibold">Background</th>
            <th className="py-2 font-semibold">Ratio</th>
            <th className="py-2 font-semibold">Body text (4.5:1)</th>
          </tr>
        </thead>
        <tbody>
          {pairs.map(([fg, bg]) => {
            const ratio = contrastRatio(palette[fg], palette[bg]);
            return (
              <tr key={`${fg}-${bg}`} className="border-b border-rule">
                <td className="py-2">{fg}</td>
                <td className="py-2">{bg}</td>
                <td className="py-2 tabular-nums">{ratio.toFixed(2)}:1</td>
                <td className="py-2">{ratio >= 4.5 ? "Passes" : "Fails"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <h2 className="mt-10 text-lg font-semibold">Type</h2>
      <dl className="mt-3 divide-y divide-rule border-y border-rule">
        {scale.map((row) => (
          <div key={row.name} className="grid grid-cols-[96px_1fr] items-baseline gap-4 py-3">
            <dt className="text-sm text-muted">
              {row.name} {row.spec}
            </dt>
            <dd className={row.className}>{row.sample}</dd>
          </div>
        ))}
        <div className="grid grid-cols-[96px_1fr] items-baseline gap-4 py-3">
          <dt className="text-sm text-muted">oracle 16/26</dt>
          <dd>
            <OracleText text="Sacrifice a creature: Scry 1. (Look at the top card of your library. You may put that card on the bottom.)" />
          </dd>
        </div>
      </dl>

      <h2 className="mt-10 text-lg font-semibold">Controls</h2>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button variant="primary">Send</Button>
        <Button>Try again</Button>
        <Button variant="ghost">Sign out</Button>
        <Button variant="danger">Delete chat</Button>
        <Button variant="primary" disabled>
          Send
        </Button>
        <ManaCost cost="{X}{2}{W/U}{B/P}{G}{C}" className="ml-4" />
      </div>
    </main>
  );
}

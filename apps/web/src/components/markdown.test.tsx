import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { CardRef } from "@/lib/api/client";
import { Markdown, safeUrl } from "./markdown";

const SEER: CardRef = {
  oracle_id: "5f5a9c5d-6b1e-4a43-9e0e-0d4b3b1f7f11",
  name: "Viscera Seer",
  image_uri: "https://cards.scryfall.io/normal/front/a/b/ab.jpg",
};
const ALTAR: CardRef = {
  oracle_id: "8d1f0a2b-3c4d-4e5f-9a0b-1c2d3e4f5a6b",
  name: "Ashnod's Altar",
  image_uri: null,
};

function renderAnswer(text: string, cards: CardRef[] = [SEER, ALTAR], streaming = false) {
  const onOpenCard = vi.fn();
  const view = render(
    <Markdown text={text} cards={cards} onOpenCard={onOpenCard} streaming={streaming} />,
  );
  return { ...view, onOpenCard };
}

describe("safeUrl", () => {
  it.each([
    ["https://scryfall.com/card/khm/168", "https://scryfall.com/card/khm/168"],
    ["http://scryfall.com", ""],
    ["javascript:alert(1)", ""],
    ["JaVaScRiPt:alert(1)", ""],
    ["  javascript:alert(1)", ""],
    ["data:text/html,<script>alert(1)</script>", ""],
    ["vbscript:msgbox(1)", ""],
    ["/v1/chats", ""],
    ["//evil.example", ""],
    ["mailto:a@b.c", ""],
  ])("%s becomes %j", (input, expected) => {
    expect(safeUrl(input)).toBe(expected);
  });
});

describe("Markdown", () => {
  it("renders basic formatting", () => {
    const { container } = renderAnswer("**Bold** and *italic*\n\n- one\n- two");
    expect(container.querySelector("strong")).toHaveTextContent("Bold");
    expect(container.querySelectorAll("li")).toHaveLength(2);
  });

  it("opens https links in a new tab without leaking the opener or referrer", () => {
    renderAnswer("See [Scryfall](https://scryfall.com/search?q=sac).");
    const link = screen.getByRole("link", { name: "Scryfall" });
    expect(link).toHaveAttribute("href", "https://scryfall.com/search?q=sac");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer nofollow");
  });

  it.each([
    "[click](javascript:alert(1))",
    "[click](JAVASCRIPT:alert(1))",
    "[click](data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==)",
    "[click](http://example.com)",
    "[click](/relative)",
    "[click][ref]\n\n[ref]: javascript:alert(1)",
    "<javascript:alert(1)>",
  ])("drops unsafe links: %s", (text) => {
    const { container } = renderAnswer(text);
    expect(container.querySelector("a")).toBeNull();
  });

  it.each([
    "<script>alert(1)</script>",
    '<img src="x" onerror="alert(1)">',
    '<a href="javascript:alert(1)">x</a>',
    '<iframe src="https://evil.example"></iframe>',
    '<svg onload="alert(1)"></svg>',
    '<div style="background:url(javascript:alert(1))">x</div>',
    'Text <b onmouseover="alert(1)">bold</b> more',
  ])("never renders raw HTML: %s", (text) => {
    const { container } = renderAnswer(text);
    expect(container.querySelector("script, img, iframe, svg, a, b, .prose-answer div")).toBeNull();
    expect(container.innerHTML).not.toMatch(/onerror|onload|onmouseover|javascript:/i);
  });

  it("renders nothing for markdown images, even https ones", () => {
    const { container } = renderAnswer("Look ![art](https://cards.scryfall.io/art.jpg) here");
    expect(container.querySelector("img")).toBeNull();
    expect(container).toHaveTextContent("Look here");
  });

  it("turns a card reference into a button that opens the card", async () => {
    const { onOpenCard } = renderAnswer(`Start with [[${SEER.oracle_id}|Viscera Seer]].`);
    await userEvent.click(screen.getByRole("button", { name: "Viscera Seer" }));
    expect(onOpenCard).toHaveBeenCalledWith(SEER);
  });

  it("labels the button with our card name, not the model's", () => {
    renderAnswer(`[[${SEER.oracle_id}|Totally Free Mana]]`);
    expect(screen.getByRole("button", { name: "Viscera Seer" })).toBeInTheDocument();
    expect(screen.queryByText("Totally Free Mana")).toBeNull();
  });

  it("matches oracle IDs case-insensitively", () => {
    renderAnswer(`[[${SEER.oracle_id.toUpperCase()}|Viscera Seer]]`);
    expect(screen.getByRole("button", { name: "Viscera Seer" })).toBeInTheDocument();
  });

  it("renders a reference that is not in the cards event as plain text", () => {
    const { container } = renderAnswer(
      "[[0e7c8a3d-1111-4222-8333-944455556666|Black Lotus]] is banned.",
    );
    expect(screen.queryByRole("button")).toBeNull();
    expect(container).toHaveTextContent("Black Lotus is banned.");
  });

  it("renders a reference with a malformed ID as plain text", () => {
    const { container } = renderAnswer(
      '[[javascript:alert(1)|Click me]] and [["><img src=x onerror=alert(1)>|Bad]]',
    );
    expect(screen.queryByRole("button")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    expect(container).toHaveTextContent("Click me");
  });

  it("finds references inside lists, emphasis and tables", () => {
    renderAnswer(
      [
        `- **[[${SEER.oracle_id}|Viscera Seer]]** first`,
        "",
        "| Card | Cost |",
        "| --- | --- |",
        `| [[${ALTAR.oracle_id}|Ashnod's Altar]] | 3 |`,
      ].join("\n"),
    );
    expect(screen.getByRole("button", { name: "Viscera Seer" })).toBeInTheDocument();
    const cell = screen.getByRole("cell", { name: "Ashnod's Altar" });
    expect(cell.querySelector("button")).not.toBeNull();
  });

  it("leaves references in code as literal text", () => {
    const { container } = renderAnswer(
      `Write \`[[${SEER.oracle_id}|Viscera Seer]]\` to link a card.`,
    );
    expect(screen.queryByRole("button")).toBeNull();
    expect(container.querySelector("code")).toHaveTextContent(`[[${SEER.oracle_id}|Viscera Seer]]`);
  });

  it("hides an unfinished reference while streaming", () => {
    const partial = `Try [[${SEER.oracle_id.slice(0, 12)}`;
    const { container, rerender } = renderAnswer(partial, [SEER], true);
    expect(container).toHaveTextContent(/^Try$/);
    rerender(
      <Markdown
        text={`Try [[${SEER.oracle_id}|Viscera Seer]]`}
        cards={[SEER]}
        onOpenCard={() => {}}
        streaming
      />,
    );
    expect(screen.getByRole("button", { name: "Viscera Seer" })).toBeInTheDocument();
  });

  it("shows unmatched brackets once streaming has finished", () => {
    const { container } = renderAnswer("Arrays look like [[1, 2]", [], false);
    expect(container).toHaveTextContent("Arrays look like [[1, 2]");
  });
});

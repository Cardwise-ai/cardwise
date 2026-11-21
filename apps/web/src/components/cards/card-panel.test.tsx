import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "@/components/ui/tooltip";
import { createApiClient } from "@/lib/api/client";
import { MOCK_ACCESS_TOKEN } from "@/lib/auth/shared";
import { apiUrl } from "@/lib/env";
import { cardByName, toCardRef } from "@/mocks/db";
import { server } from "@/mocks/node";
import { CardPanel } from "./card-panel";

vi.mock("@/lib/api/browser", () => {
  const client = createApiClient({
    baseUrl: apiUrl,
    getAccessToken: async () => MOCK_ACCESS_TOKEN,
  });
  return { getApiClient: () => client };
});

function renderPanel(name: string) {
  const card = toCardRef(cardByName(name));
  render(
    <TooltipProvider>
      <CardPanel card={card} onClose={() => {}} variant="docked" />
    </TooltipProvider>,
  );
  return card;
}

describe("CardPanel", () => {
  it("shows the card's cost, type, oracle text and facts", async () => {
    renderPanel("Viscera Seer");
    const heading = await screen.findByRole("heading", { name: "Viscera Seer", level: 2 });
    expect(heading).toHaveFocus();
    expect(screen.getByRole("img", { name: "Viscera Seer" })).toHaveAttribute(
      "src",
      expect.stringMatching(/^https:\/\/cards\.scryfall\.io\//),
    );
    expect(screen.getByText("Creature — Vampire Wizard")).toBeInTheDocument();
    expect(screen.getByText(/Sacrifice a creature: Scry 1\./)).toBeInTheDocument();
    const facts = screen.getByText("Color identity").closest("dl")!;
    expect(within(facts).getByText("Black")).toBeInTheDocument();
    expect(within(facts).getByText("Legal")).toBeInTheDocument();
    expect(within(facts).getByText("Sacrifice outlet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open on Scryfall/ })).toHaveAttribute(
      "href",
      expect.stringMatching(/^https:\/\/scryfall\.com\//),
    );
  });

  it("flips between the faces of a double-faced card", async () => {
    renderPanel("Esika, God of the Tree // The Prismatic Bridge");
    await screen.findByRole("heading", { name: "Esika, God of the Tree", level: 2 });
    const back = screen.getByRole("button", { name: "Back" });
    expect(back).toHaveAttribute("aria-pressed", "false");
    await userEvent.click(back);
    expect(back).toHaveAttribute("aria-pressed", "true");
    expect(
      screen.getByRole("heading", { name: "The Prismatic Bridge", level: 2 }),
    ).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "The Prismatic Bridge" })).toBeInTheDocument();
  });

  it("stacks both halves of a split card", async () => {
    renderPanel("Fire // Ice");
    await screen.findByRole("heading", { name: "Fire // Ice", level: 2 });
    expect(screen.getByRole("heading", { name: "Fire", level: 3 })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Ice", level: 3 })).toBeInTheDocument();
  });

  it("offers a retry when the card fails to load", async () => {
    let fail = true;
    server.use(
      http.get(`${apiUrl}/v1/cards/:id`, () => {
        if (!fail) return undefined;
        return HttpResponse.json(
          { error: { code: "internal", message: "Database unavailable.", request_id: "req_1" } },
          { status: 500 },
        );
      }),
    );
    renderPanel("Carrion Feeder");
    expect(await screen.findByText("Couldn't load Carrion Feeder.")).toBeInTheDocument();
    fail = false;
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(
      await screen.findByRole("heading", { name: "Carrion Feeder", level: 2 }),
    ).toBeInTheDocument();
  });
});

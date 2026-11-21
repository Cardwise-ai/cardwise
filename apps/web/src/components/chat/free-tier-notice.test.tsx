import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { TooltipProvider } from "@/components/ui/tooltip";
import { FREE_TIER_NOTICE_KEY, FreeTierNotice, resetFreeTierNotice } from "./free-tier-notice";

function renderNotice() {
  return render(
    <TooltipProvider>
      <div>
        <FreeTierNotice />
        <textarea aria-label="Message" />
      </div>
    </TooltipProvider>,
  );
}

describe("FreeTierNotice", () => {
  afterEach(() => {
    window.localStorage.clear();
    resetFreeTierNotice();
  });

  it("explains free tiers and the hourly limit", () => {
    renderNotice();
    expect(screen.getByRole("note", { name: "About free model tiers" })).toHaveTextContent(
      "Cardwise runs on free model tiers, so answers can be slower or shorter when it's busy. You can send 20 messages an hour.",
    );
  });

  it("stays dismissed after a reload and moves focus to the composer", async () => {
    const first = renderNotice();
    await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Message" })).toHaveFocus();
    expect(window.localStorage.getItem(FREE_TIER_NOTICE_KEY)).toBe("1");

    first.unmount();
    resetFreeTierNotice();
    renderNotice();
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
  });
});

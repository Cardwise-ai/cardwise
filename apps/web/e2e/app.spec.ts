import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";
import { SEEDED_CHAT_ID } from "../src/mocks/db";
import { signIn } from "./helpers";

async function expectNoAxeViolations(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  const summary = results.violations.map(
    (v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`,
  );
  expect(summary).toEqual([]);
}

test.describe("chat", () => {
  test.beforeEach(async ({ page }) => {
    await signIn(page);
  });

  test("starts a chat, streams an answer and opens a referenced card", async ({ page }) => {
    await page.getByRole("button", { name: /best free sacrifice outlets/ }).click();
    await expect(page).toHaveURL(/\/chats\/[0-9a-f-]{36}$/);
    const answer = page.getByRole("log", { name: "Messages" });
    await expect(answer.getByRole("list", { name: "Cards in this answer" })).toBeVisible({
      timeout: 20_000,
    });
    await expect(page.getByRole("button", { name: "Send" })).toBeVisible();

    await answer.getByRole("button", { name: "Viscera Seer", exact: true }).first().click();
    await expect(page.getByRole("heading", { name: "Viscera Seer", level: 2 })).toBeVisible();
    await expect(page.getByText(/^Sacrifice a creature: Scry 1\./)).toBeVisible();
  });

  test("stops an answer and keeps what arrived", async ({ page }) => {
    await page.goto(`/chats/${SEEDED_CHAT_ID}`);
    await page
      .getByRole("textbox", { name: "Message" })
      .fill("Which finishers would you add for Selvala?");
    await page.keyboard.press("Enter");
    await expect(page.getByRole("button", { name: "Stop" })).toBeVisible();
    await page.getByRole("button", { name: "Stop" }).click();
    await expect(page.getByText("Stopped. The answer above is incomplete.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Ask again" })).toBeVisible();
  });

  test("puts the message back when the API refuses it", async ({ page }) => {
    await page.goto(`/chats/${SEEDED_CHAT_ID}`);
    const box = page.getByRole("textbox", { name: "Message" });
    await box.fill("Does this hit the rate limit?");
    await page.keyboard.press("Enter");
    await expect(page.getByText(/Too many messages this hour/)).toBeVisible();
    await expect(box).toHaveValue("Does this hit the rate limit?");
  });

  test("says when another answer is still streaming", async ({ page }) => {
    await page.goto(`/chats/${SEEDED_CHAT_ID}`);
    await page.getByRole("textbox", { name: "Message" }).fill("Still busy in another tab?");
    await page.keyboard.press("Enter");
    await expect(page.getByText(/still answering another message/)).toBeVisible();
  });

  test("keeps a cut-off answer and offers to try again", async ({ page }) => {
    await page.goto(`/chats/${SEEDED_CHAT_ID}`);
    await page
      .getByRole("textbox", { name: "Message" })
      .fill("Finishers for Selvala, and drop the connection");
    await page.keyboard.press("Enter");
    await expect(
      page.getByText("The connection dropped before the answer finished. Try again."),
    ).toBeVisible({ timeout: 20_000 });
    await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();
  });

  test("the free-tier notice stays dismissed", async ({ page }) => {
    const notice = page.getByRole("note", { name: "About free model tiers" });
    await expect(notice).toContainText("You can send 20 messages an hour.");
    await notice.getByRole("button", { name: "Dismiss" }).click();
    await expect(notice).toHaveCount(0);
    await expect(page.getByRole("textbox", { name: "Message" })).toBeFocused();
    await page.goto(`/chats/${SEEDED_CHAT_ID}`);
    await expect(page.getByRole("textbox", { name: "Message" })).toBeVisible();
    await expect(notice).toHaveCount(0);
  });

  test("renames and deletes a chat", async ({ page, isMobile }) => {
    await page.goto(`/chats/${SEEDED_CHAT_ID}`);
    const header = page.locator("header", { has: page.getByRole("heading", { level: 1 }) });
    await header.getByRole("button", { name: /^Options for / }).click();
    await page.getByRole("menuitem", { name: "Rename" }).click();
    const dialog = page.getByRole("dialog", { name: "Rename chat" });
    await dialog.getByLabel("Title").fill("Meren sac outlets");
    await dialog.getByRole("button", { name: "Save" }).click();
    await expect(page.getByRole("heading", { name: "Meren sac outlets", level: 1 })).toBeVisible();

    await header.getByRole("button", { name: /^Options for / }).click();
    await page.getByRole("menuitem", { name: "Delete chat" }).click();
    await page
      .getByRole("dialog", { name: "Delete this chat?" })
      .getByRole("button", { name: "Delete chat" })
      .click();
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByText("Chat deleted", { exact: true })).toBeVisible();
    if (isMobile) await page.getByRole("button", { name: "Show chats" }).click();
    await expect(page.getByRole("link", { name: "Meren sac outlets" })).toHaveCount(0);
  });
});

test.describe("accessibility", () => {
  test("sign-in has no axe violations", async ({ page }) => {
    await page.goto("/sign-in");
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
    await expectNoAxeViolations(page);
  });

  test("new chat has no axe violations", async ({ page }) => {
    await signIn(page);
    await expect(
      page.getByRole("heading", { name: "Ask about cards for your deck" }),
    ).toBeVisible();
    await expect(page.getByRole("note", { name: "About free model tiers" })).toBeVisible();
    await expectNoAxeViolations(page);
  });

  test("a conversation with the card panel open has no axe violations", async ({ page }) => {
    await signIn(page);
    await page.goto(`/chats/${SEEDED_CHAT_ID}`);
    await expect(page.getByRole("list", { name: "Cards in this answer" })).toBeVisible();
    await expectNoAxeViolations(page);

    await page
      .getByRole("log")
      .getByRole("button", { name: "Viscera Seer", exact: true })
      .first()
      .click();
    await expect(page.getByRole("heading", { name: "Viscera Seer", level: 2 })).toBeVisible();
    await expectNoAxeViolations(page);
  });
});

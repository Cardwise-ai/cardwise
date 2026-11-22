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

async function expectBlankEditableComposer(page: Page) {
  const visibleTextareas = await page.locator("textarea").evaluateAll((textareas) =>
    textareas
      .filter((textarea) => textarea.getClientRects().length > 0)
      .map((textarea) => ({
        value: (textarea as HTMLTextAreaElement).value,
        disabled: (textarea as HTMLTextAreaElement).disabled,
      })),
  );
  expect(visibleTextareas).toEqual([{ value: "", disabled: false }]);

  const composer = page.getByRole("textbox", { name: "Message" });
  await expect(composer).toHaveValue("");
  await expect(composer).toBeEnabled();
  await composer.fill("A different Meren question");
  await expect(composer).toHaveValue("A different Meren question");
}

async function clickNewChat(page: Page, isMobile: boolean) {
  const sidebar = isMobile ? page.getByRole("dialog", { name: "Chats" }) : page.locator("aside");
  await sidebar.locator('a[href="/"]').filter({ hasText: "New chat" }).click();
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

  test("names a new chat after its first message", async ({ page, isMobile }) => {
    await page.getByRole("textbox", { name: "Message" }).fill("Ramp for my Esika deck?");
    await page.getByRole("button", { name: "Send" }).click();
    await expect(page).toHaveURL(/\/chats\/[0-9a-f-]{36}$/);
    await expect(
      page.getByRole("heading", { level: 1, name: "Ramp for my Esika deck?" }),
    ).toBeVisible();

    if (isMobile) await page.getByRole("button", { name: "Show chats" }).click();
    const sidebar = isMobile ? page.getByRole("dialog", { name: "Chats" }) : page.locator("aside");
    await expect(sidebar.getByRole("link", { name: "Ramp for my Esika deck?" })).toBeVisible();
  });
  test("starts a fresh chat after an answer and can edit its composer", async ({
    page,
    isMobile,
  }) => {
    const composer = page.getByRole("textbox", { name: "Message" });
    await composer.fill("What should I add to my Meren deck?");
    await page.getByRole("button", { name: "Send" }).click();
    await expect(page).toHaveURL(/\/chats\/[0-9a-f-]{36}$/);
    await expect(
      page
        .getByRole("log", { name: "Messages" })
        .getByRole("list", { name: "Cards in this answer" }),
    ).toBeVisible({ timeout: 20_000 });

    if (isMobile) await page.getByRole("button", { name: "Show chats" }).click();
    await clickNewChat(page, isMobile);

    await expect(page).toHaveURL("/");
    await expectBlankEditableComposer(page);
  });

  test("starts a fresh chat while the previous answer is streaming", async ({ page, isMobile }) => {
    const composer = page.getByRole("textbox", { name: "Message" });
    await composer.fill("What should I add to my Meren deck?");
    await page.getByRole("button", { name: "Send" }).click();
    await expect(page).toHaveURL(/\/chats\/[0-9a-f-]{36}$/);
    await expect(page.getByRole("button", { name: "Stop" })).toBeVisible();

    if (isMobile) await page.getByRole("button", { name: "Show chats" }).click();
    await clickNewChat(page, isMobile);

    await expect(page).toHaveURL("/");
    await expectBlankEditableComposer(page);
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
      page.getByRole("heading", { name: "What is your deck trying to do?" }),
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

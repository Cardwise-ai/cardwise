import { expect, type Page, test } from "@playwright/test";
import { SEEDED_CHAT_ID } from "../src/mocks/db";
import { signIn } from "./helpers";

// Captures the main screens for design review. Runs only when SCREENSHOT_DIR is set:
//   SCREENSHOT_DIR=../screens pnpm test:e2e screens
const dir = process.env.SCREENSHOT_DIR;
test.skip(!dir, "Set SCREENSHOT_DIR to capture screens");

async function shot(page: Page, name: string, project: string) {
  await page.waitForTimeout(250);
  await page.screenshot({ path: `${dir}/${project}-${name}.png`, fullPage: false });
}

test("capture screens", async ({ page }, info) => {
  const project = info.project.name;
  const mobile = project === "mobile";

  await page.goto("/sign-in");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await shot(page, "1-sign-in", project);

  await signIn(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Ask about cards for your deck" })).toBeVisible();
  if (!mobile)
    await expect(page.getByRole("link", { name: "Sacrifice outlets for Meren" })).toBeVisible();
  await shot(page, "2-new-chat", project);

  await page.goto(`/chats/${SEEDED_CHAT_ID}`);
  await expect(page.getByRole("list", { name: "Cards in this answer" })).toBeVisible();
  await page.waitForLoadState("networkidle");
  await shot(page, "3-conversation", project);

  await page.getByRole("button", { name: "Viscera Seer", exact: true }).first().click();
  await expect(page.getByRole("heading", { name: "Viscera Seer", level: 2 })).toBeVisible();
  await page.waitForLoadState("networkidle");
  await shot(page, "4-card-panel", project);

  if (mobile) {
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "Show chats" }).click();
    await expect(page.getByRole("dialog", { name: "Chats" })).toBeVisible();
    await shot(page, "5-chat-drawer", project);
    await page.keyboard.press("Escape");
  }

  await page
    .getByRole("textbox", { name: "Message" })
    .fill("Which finishers would you add for Selvala?");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("Searching cards…")).toBeVisible();
  await shot(page, "6-streaming", project);
  await expect(page.getByRole("list", { name: "Cards in this answer" })).toHaveCount(2, {
    timeout: 20_000,
  });

  await page.goto(`/chats/${SEEDED_CHAT_ID}`);
  await page.getByRole("textbox", { name: "Message" }).fill("Good ramp for Esika?");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(
    page.getByRole("button", { name: "Show Esika, God of the Tree // The Prismatic Bridge" }),
  ).toBeVisible({
    timeout: 20_000,
  });
  await page
    .getByRole("button", { name: "Show Esika, God of the Tree // The Prismatic Bridge" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Esika, God of the Tree", level: 2 }),
  ).toBeVisible();
  await page.waitForLoadState("networkidle");
  await shot(page, "7-dfc-card", project);

  await page.goto(`/chats/${SEEDED_CHAT_ID}`);
  await page.getByRole("textbox", { name: "Message" }).fill("Testing the rate limit");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText(/Too many messages this hour/)).toBeVisible();
  await shot(page, "8-rate-limited", project);

  await page.goto("/tokens");
  await shot(page, "9-tokens", project);
});

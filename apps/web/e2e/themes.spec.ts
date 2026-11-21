import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";
import { SEEDED_CHAT_ID } from "../src/mocks/db";
import { signIn } from "./helpers";

async function expectNoAxeViolations(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  const summary = results.violations.map(
    (violation) =>
      `${violation.id}: ${violation.nodes.map((node) => node.target.join(" ")).join(", ")}`,
  );
  expect(summary).toEqual([]);
}

test("theme toggle follows system, saves explicit choices, and restores system mode", async ({
  page,
}) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto("/sign-in");
  const root = page.locator("html");
  await expect(root).toHaveAttribute("data-theme-mode", "system");
  await expect(root).toHaveAttribute("data-theme", "dark");

  await page.getByRole("button", { name: /^Theme: System/ }).click();
  await expect(root).toHaveAttribute("data-theme-mode", "light");
  await expect(root).toHaveAttribute("data-theme", "light");
  expect(await page.evaluate(() => localStorage.getItem("cardwise.theme"))).toBe("light");

  await page.reload();
  await expect(root).toHaveAttribute("data-theme", "light");
  await page.getByRole("button", { name: /^Theme: Light/ }).click();
  await expect(root).toHaveAttribute("data-theme", "dark");
  expect(await page.evaluate(() => localStorage.getItem("cardwise.theme"))).toBe("dark");

  await page.reload();
  await expect(root).toHaveAttribute("data-theme", "dark");
  await page.getByRole("button", { name: /^Theme: Dark/ }).click();
  await expect(root).toHaveAttribute("data-theme-mode", "system");
  expect(await page.evaluate(() => localStorage.getItem("cardwise.theme"))).toBeNull();

  await page.emulateMedia({ colorScheme: "light" });
  await expect(root).toHaveAttribute("data-theme", "light");
});

for (const theme of ["light", "dark"] as const) {
  test(`the ${theme} theme is accessible across sign-in, chat, cards and dialogs`, async ({
    page,
    isMobile,
  }) => {
    await page.emulateMedia({ colorScheme: theme });
    await page.goto("/sign-in");
    await page.evaluate((preference) => localStorage.setItem("cardwise.theme", preference), theme);
    await page.reload();
    await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
    await expectNoAxeViolations(page);
    await page.goto("/sign-in?error=google");
    await expectNoAxeViolations(page);

    await signIn(page);
    await page.goto("/");
    if (isMobile) {
      await page.getByRole("button", { name: "Show chats" }).click();
      await expect(
        page.getByRole("button", { name: new RegExp(`^Theme: ${theme}`, "i") }),
      ).toBeVisible();
      await page.keyboard.press("Escape");
    } else {
      await expect(
        page.getByRole("button", { name: new RegExp(`^Theme: ${theme}`, "i") }),
      ).toBeVisible();
    }
    await expectNoAxeViolations(page);

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
    if (isMobile) await page.keyboard.press("Escape");

    const header = page.locator("header", { has: page.getByRole("heading", { level: 1 }) });
    await header.getByRole("button", { name: /^Options for / }).click();
    await page.getByRole("menuitem", { name: "Rename" }).click();
    await expect(page.getByRole("dialog", { name: "Rename chat" })).toBeVisible();
    await expectNoAxeViolations(page);
  });
}

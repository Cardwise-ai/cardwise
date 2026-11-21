import type { Page } from "@playwright/test";

export const TEST_EMAIL = "reader@example.com";

/** Signs in through the real form. In mock mode any email and password work. */
export async function signIn(page: Page, email = TEST_EMAIL): Promise<void> {
  await page.goto("/sign-in");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("correct horse battery staple");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL((url) => url.pathname === "/");
}

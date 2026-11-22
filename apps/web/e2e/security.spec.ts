import { expect, test } from "@playwright/test";
import { EXPIRED_SESSION_CHAT_ID, SEEDED_CHAT_ID } from "../src/mocks/db";
import { signIn } from "./helpers";

test.describe("security headers", () => {
  test("every page carries a nonce-based CSP and hardening headers", async ({ page }) => {
    const response = await page.goto("/sign-in");
    const headers = response!.headers();

    const csp =
      headers["content-security-policy-report-only"] ?? headers["content-security-policy"];
    expect(csp, "CSP header").toBeTruthy();
    const nonce = /'nonce-([^']+)'/.exec(csp!)?.[1];
    expect(nonce).toBeTruthy();
    expect(csp).toContain("'strict-dynamic'");
    expect(csp).not.toMatch(/script-src[^;]*'unsafe-inline'/);
    expect(csp).toContain("img-src 'self' https://cards.scryfall.io");
    expect(csp).toContain("frame-ancestors 'none'");

    expect(headers["strict-transport-security"]).toContain("max-age=");
    expect(headers["x-content-type-options"]).toBe("nosniff");
    expect(headers["x-frame-options"]).toBe("DENY");
    expect(headers["referrer-policy"]).toBe("strict-origin-when-cross-origin");
    expect(headers["permissions-policy"]).toContain("camera=()");
    expect(headers["x-powered-by"]).toBeUndefined();

    // Every script Next.js rendered carries this response's nonce.
    const scriptNonces = await page
      .locator("script")
      .evaluateAll((scripts) => scripts.map((s) => (s as HTMLScriptElement).nonce));
    expect(scriptNonces.length).toBeGreaterThan(0);
    for (const value of scriptNonces) expect(value).toBe(nonce);
  });

  test("a fresh nonce is issued per request", async ({ request }) => {
    const nonceOf = async () => {
      const response = await request.get("/sign-in");
      const csp = response.headers()["content-security-policy-report-only"] ?? "";
      return /'nonce-([^']+)'/.exec(csp)?.[1];
    };
    expect(await nonceOf()).not.toBe(await nonceOf());
  });

  test("an injected inline event handler is reported as a violation", async ({ page }) => {
    await page.goto("/sign-in");
    const violation = await page.evaluate(
      () =>
        new Promise<string>((resolve) => {
          document.addEventListener(
            "securitypolicyviolation",
            (event) => resolve(event.effectiveDirective),
            {
              once: true,
            },
          );
          // 'strict-dynamic' trusts scripts created from script, so test the classic XSS shape instead.
          const target = document.createElement("div");
          target.setAttribute("onclick", "window.__injected = true");
          document.body.append(target);
          target.click();
          setTimeout(() => resolve("none"), 2000);
        }),
    );
    expect(violation).toMatch(/^script-src/);
  });
});

test.describe("sign-in", () => {
  test("signed-out visitors are sent to sign in and come back afterwards", async ({ page }) => {
    await page.goto("/chats/6f1c2a9e-3b4d-4e5f-8a7b-1c2d3e4f5a6b");
    await expect(page).toHaveURL(/\/sign-in\?next=%2Fchats%2F6f1c2a9e/);
    await page.getByLabel("Email").fill("reader@example.com");
    await page.getByLabel("Password").fill("hunter22hunter22");
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(page).toHaveURL(/\/chats\/6f1c2a9e-3b4d-4e5f-8a7b-1c2d3e4f5a6b$/);
    await expect(
      page.getByRole("heading", { name: "Sacrifice outlets for Meren", level: 1 }),
    ).toBeVisible();
  });

  test("Google sign-in returns to the requested chat in mock mode", async ({ page }) => {
    await page.goto(`/sign-in?next=%2Fchats%2F${SEEDED_CHAT_ID}`);
    await page.getByRole("button", { name: "Continue with Google" }).click();
    await expect(page).toHaveURL(new RegExp(`/chats/${SEEDED_CHAT_ID}$`));
    await expect(page.getByRole("heading", { name: "Sacrifice outlets for Meren" })).toBeVisible();
  });

  test("email-link sign-in still returns to the requested chat in mock mode", async ({ page }) => {
    await page.goto(`/sign-in?next=%2Fchats%2F${SEEDED_CHAT_ID}`);
    await page.getByLabel("Email").fill("reader@example.com");
    await page.getByRole("button", { name: "Email me a sign-in link" }).click();
    await expect(page).toHaveURL(new RegExp(`/chats/${SEEDED_CHAT_ID}$`));
    await expect(page.getByRole("heading", { name: "Sacrifice outlets for Meren" })).toBeVisible();
  });

  test("an off-site next parameter is ignored", async ({ page }) => {
    await page.goto("/sign-in?next=//evil.example/steal");
    await page.getByLabel("Email").fill("reader@example.com");
    await page.getByLabel("Password").fill("hunter22hunter22");
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(page).toHaveURL(/^http:\/\/localhost:\d+\/$/);
  });

  test("signing out ends the session", async ({ page, isMobile }) => {
    await signIn(page);
    if (isMobile) await page.getByRole("button", { name: "Show chats" }).click();
    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page).toHaveURL(/\/sign-in$/);
    await page.goto("/");
    await expect(page).toHaveURL(/\/sign-in$/);
  });

  test("a session the API refuses is ended and the reader is asked to sign in", async ({
    page,
  }) => {
    await signIn(page);
    await page.goto(`/chats/${EXPIRED_SESSION_CHAT_ID}`);
    await expect(page).toHaveURL(/\/sign-in\?error=session&next=%2Fchats%2F00000000-/);
    await expect(
      page.getByText("Your session has ended. Sign in again to continue."),
    ).toBeVisible();
    await page.goto("/");
    await expect(page).toHaveURL(/\/sign-in$/);
  });
});

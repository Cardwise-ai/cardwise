import { defineConfig, devices } from "@playwright/test";

const port = 3100;
const externalUrl = process.env.PLAYWRIGHT_BASE_URL;

/**
 * End-to-end tests run against a production build in mock mode: MSW stands in for the API and a
 * cookie stands in for Supabase. Set PLAYWRIGHT_BASE_URL to test a server you started yourself.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: externalUrl ?? `http://localhost:${port}`,
    trace: "retain-on-failure",
    locale: "en-US",
    timezoneId: "UTC",
  },
  projects: [
    {
      name: "desktop",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
    { name: "mobile", use: { ...devices["Pixel 7"] } },
  ],
  ...(externalUrl
    ? {}
    : {
        webServer: {
          command: `pnpm exec msw init public --no-save && node scripts/with-mocks.mjs next build && node scripts/with-mocks.mjs next start -p ${port}`,
          url: `http://localhost:${port}/sign-in`,
          timeout: 300_000,
          reuseExistingServer: !process.env.CI,
        },
      }),
});

import { defineConfig } from "@playwright/test";

/** The whole system in a browser (ADR 0031). Start it first: stack/up.sh, then stack/apps.sh. One
 * worker: the steps of the journey build on each other, like a day on campus. */
export default defineConfig({
  testDir: "tests",
  timeout: 180_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0, // in serial mode a retry replays the whole journey
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    // Locally the installed Chrome; in CI the Chromium that `playwright install` downloads.
    channel: process.env.CI ? undefined : "chrome",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});

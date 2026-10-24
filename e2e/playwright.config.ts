import { defineConfig, devices } from "@playwright/test";

import { stack } from "./tests/support";

/**
 * Real-browser acceptance tests.
 *
 * They need the isolated acceptance stack (never the development database):
 *
 *   backend\.venv\Scripts\python.exe -m scripts.seed_acceptance   (from backend\)
 *   backend\.venv\Scripts\python.exe scripts\acceptance_stack.py
 *
 * `E2E_WEB_URL` overrides the address recorded by the stack launcher.
 */
export default defineConfig({
  testDir: "./tests",
  globalSetup: "./tests/global-setup.ts",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: stack().web,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "webkit", use: { ...devices["Desktop Safari"] } },
    // Opt-in: Playwright's Firefox 155 build does not start on the author's Windows machine
    // ("mozglue" side-by-side error), so it is excluded unless E2E_FIREFOX=1 is set.
    ...(process.env.E2E_FIREFOX
      ? [{ name: "firefox", use: { ...devices["Desktop Firefox"] } }]
      : []),
  ],
});

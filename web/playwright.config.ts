import { defineConfig, devices } from "@playwright/test";

/**
 * Smoke flow against a fresh API (in-memory-ish SQLite in a temp file) and the
 * Next dev server. `npm run e2e` starts both; CI sets PW_BASE_URL/API_URL to
 * reuse running servers instead.
 */
const API = process.env.API_URL || "http://localhost:8011";
const WEB = process.env.PW_BASE_URL || "http://localhost:3011";

export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  expect: { timeout: 15_000 },
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: { baseURL: WEB, trace: "retain-on-failure", ...devices["Desktop Chrome"] },
  webServer: [
    {
      command: `cd ../cloud && DATABASE_URL=sqlite:////tmp/raqib_e2e.db CLIPS_DIR=/tmp/raqib_e2e_clips CORS_ORIGINS=${WEB} uv run --no-sync uvicorn raqib_api.main:app --port 8011`,
      url: `${API}/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command: `NEXT_PUBLIC_API_URL=${API} npx next dev -p 3011`,
      url: `${WEB}/en`,
      reuseExistingServer: !process.env.CI,
      timeout: 180_000,
    },
  ],
});

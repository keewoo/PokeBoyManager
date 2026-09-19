import { defineConfig, devices } from "@playwright/test";

const WEB_PORT = 3100;
const API_PORT = 8100;
const MAILPIT_UI_PORT = process.env.MAILPIT_UI_PORT || "58025";

export const WEB_BASE_URL = `http://localhost:${WEB_PORT}`;
export const API_BASE_URL = `http://localhost:${API_PORT}`;
export const MAILPIT_BASE_URL = `http://localhost:${MAILPIT_UI_PORT}`;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["html", { open: "never" }]] : "list",
  use: {
    baseURL: WEB_BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "uv run uvicorn pbm_api.main:app --host 0.0.0.0 --port " + API_PORT,
      cwd: "../api",
      url: `${API_BASE_URL}/health`,
      reuseExistingServer: !process.env.CI,
      env: {
        DATABASE_URL:
          process.env.E2E_DATABASE_URL ||
          "postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_v1_pages_auth_e2e",
        REDIS_URL: process.env.REDIS_URL || "redis://localhost:56379/0",
        REDIS_PREFIX: "pbm:v1-pages-auth:e2e:",
        SMTP_HOST: process.env.SMTP_HOST || "localhost",
        SMTP_PORT: process.env.SMTP_PORT || "51025",
        APP_PUBLIC_URL: WEB_BASE_URL,
      },
    },
    {
      // `next start` (build de production) plutôt que `next dev` : la compilation à la
      // demande de `next dev` introduit des pauses variables en cours d'interaction que
      // Playwright interprète comme un élément instable, et fait échouer les tests au hasard.
      command: `pnpm exec next build && pnpm exec next start --port ${WEB_PORT}`,
      url: WEB_BASE_URL,
      reuseExistingServer: !process.env.CI,
      timeout: 180_000,
      env: {
        NEXT_PUBLIC_API_URL: API_BASE_URL,
      },
    },
  ],
});

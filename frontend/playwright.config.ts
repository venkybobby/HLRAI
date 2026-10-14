import { defineConfig } from "@playwright/test";

// Runs the real FastAPI service (read-only S1 needs no models) behind the built front end.
// HLRAI_CHROMIUM lets a sandbox point at a preinstalled browser; elsewhere run `npx playwright install chromium`.
const exe = process.env.HLRAI_CHROMIUM;
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  use: { baseURL: "http://127.0.0.1:5173", launchOptions: exe ? { executablePath: exe } : {} },
  webServer: [
    {
      command: "python -m uvicorn backend.app.main:app --port 8000",
      cwd: "..",
      url: "http://127.0.0.1:8000/api/v1/register",
      reuseExistingServer: !process.env.CI,
    },
    {
      command: "npm run build && npx vite preview --host 127.0.0.1",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: !process.env.CI,
    },
  ],
});

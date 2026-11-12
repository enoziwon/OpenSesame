import { defineConfig } from "@playwright/test";
export default defineConfig({
  timeout: 120000,
  testDir: "./tests",
  use: { baseURL: "http://127.0.0.1:5173", browserName: "chromium" },
  webServer: {
    command: "npm run dev -- --host 127.0.0.1",
    url: "http://127.0.0.1:5173",
    reuseExistingServer: true,
  },
  workers: 1,
});

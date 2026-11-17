import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/integration",
  timeout: 60000,
  workers: 1,
  use: { baseURL: "http://127.0.0.1:15173", browserName: "chromium" },
  webServer: [
    {
      command: `${process.platform === "win32" ? "..\\.venv\\Scripts\\python.exe" : "../.venv/bin/python"} -m uvicorn src.final.app:app --app-dir .. --host 127.0.0.1 --port 18001`,
      url: "http://127.0.0.1:18001/health",
      env: { OPENSESAME_OCR: "clova", OPENSESAME_FINAL_FALLBACK: "" },
      reuseExistingServer: false,
    },
    {
      command: "npm run dev -- --host 127.0.0.1 --port 15173 --strictPort",
      url: "http://127.0.0.1:15173",
      env: { VITE_API_BASE_URL: "http://127.0.0.1:18001" },
      reuseExistingServer: false,
    },
  ],
});

import { defineConfig, devices } from "@playwright/test";
import { existsSync } from "node:fs";

const python = existsSync("../.test-venv/bin/python") ? "../.test-venv/bin/python" : "python";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: "http://127.0.0.1:7331",
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `PYTHONPATH=../src ASKSQL_CONFIG_DIR=/tmp/asksql-studio-e2e ${python} -m asksql ui --no-open`,
    url: "http://127.0.0.1:7331/api/health",
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});

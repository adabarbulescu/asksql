import { defineConfig, devices } from "@playwright/test";
import { existsSync } from "node:fs";

const python = existsSync("../.test-venv/bin/python")
  ? "../.test-venv/bin/python"
  : existsSync("../.venv/bin/python")
    ? "../.venv/bin/python"
    : "python3";
const port = process.env.ASKSQL_E2E_PORT ?? "17331";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `PYTHONPATH=../src ASKSQL_CONFIG_DIR=/tmp/asksql-studio-e2e ${python} -m asksql ui --port ${port} --no-open`,
    url: `http://127.0.0.1:${port}/api/health`,
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});

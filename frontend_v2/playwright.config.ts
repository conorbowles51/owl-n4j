import { defineConfig, devices } from "@playwright/test"

export default defineConfig({
  testDir: "./e2e",
  outputDir: "./test-results/brand-smoke",
  fullyParallel: false,
  timeout: 30_000,
  expect: {
    timeout: 10_000,
  },
  use: {
    baseURL: "http://127.0.0.1:5176",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    viewport: { width: 1440, height: 900 },
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 5176 --strictPort",
    url: "http://127.0.0.1:5176",
    reuseExistingServer: false,
    timeout: 120_000,
  },
})

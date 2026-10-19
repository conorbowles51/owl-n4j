import "@/styles/globals.css"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, cleanup, render, screen, within } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { page } from "vitest/browser"
import { platformUpdateAPI, type PlatformUpdateStatus } from "../api"
import { PlatformUpdatesPage } from "./PlatformUpdatesPage"

vi.mock("../api", () => ({
  platformUpdateAPI: { getStatus: vi.fn(), check: vi.fn(), deploy: vi.fn() },
}))
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }))
const available: PlatformUpdateStatus = {
  enabled: true,
  configured: true,
  can_deploy: true,
  repo_dir: "/opt/synthetic-loupe",
  remote: "origin",
  branch: "main",
  service_name: "synthetic-self-update.service",
  update_available: true,
  local_sha: "a".repeat(40),
  local_short_sha: "aaaaaaa",
  remote_sha: "b".repeat(40),
  remote_short_sha: "bbbbbbb",
  last_checked_at: "2026-09-25T12:00:00Z",
  deployment_running: false,
  deployment_status: "idle",
}
let client: QueryClient
afterEach(() => {
  cleanup()
  client?.clear()
  vi.resetAllMocks()
})

for (const width of [1280, 390]) {
  it(`shows plain-language status and preserves the explicit manual update recovery journey at ${width}px`, async () => {
    await page.viewport(width, 900)
    vi.mocked(platformUpdateAPI.getStatus).mockResolvedValue({
      ...available,
      configured: false,
      can_deploy: false,
      config_error: "sudo: synthetic service access denied",
      deploy_log_tail: "Synthetic stored diagnostic only",
    })
    vi.mocked(platformUpdateAPI.check).mockResolvedValue(available)
    vi.mocked(platformUpdateAPI.deploy).mockRejectedValue(
      Error("synthetic lost response")
    )
    client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    await act(async () => {
      render(
        <QueryClientProvider client={client}>
          <main>
            <PlatformUpdatesPage />
          </main>
        </QueryClientProvider>
      )
    })
    await expect
      .element(page.getByText("Manual update unavailable", { exact: true }))
      .toBeVisible()
    expect(
      screen.getByText("sudo: synthetic service access denied")
    ).not.toBeVisible()
    expect(
      screen.getByText("Synthetic stored diagnostic only")
    ).not.toBeVisible()
    expect(
      screen.getByText(/Published improvements are deployed automatically/)
    ).toBeVisible()
    expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(width)
    await page.screenshot({
      path: `/private/tmp/loupe-updates-${width}-overview.png`,
    })
    await act(async () => {
      await page
        .getByText("Technical details for administrators", { exact: true })
        .click()
    })
    await expect
      .element(
        page.getByText("sudo: synthetic service access denied", { exact: true })
      )
      .toBeVisible()
    expect(screen.getByText("Synthetic stored diagnostic only")).toBeVisible()
    expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(width)
    await act(async () => {
      await page
        .getByText("Technical details for administrators", { exact: true })
        .click()
    })
    await act(async () => {
      await page
        .getByRole("button", { name: "Check for updates", exact: true })
        .click()
    })
    await expect
      .element(page.getByText("Manual update available", { exact: true }))
      .toBeVisible()
    await act(async () => {
      await page
        .getByRole("button", { name: "Start manual update", exact: true })
        .click()
    })
    await expect.element(page.getByRole("dialog")).toBeVisible()
    expect(
      within(screen.getByRole("dialog")).getByText("aaaaaaa")
    ).not.toBeVisible()
    await act(async () => {
      await page.getByRole("button", { name: "Cancel", exact: true }).click()
    })
    expect(platformUpdateAPI.deploy).not.toHaveBeenCalled()
    await act(async () => {
      await page
        .getByRole("button", { name: "Start manual update", exact: true })
        .click()
    })
    await act(async () => {
      await page
        .getByRole("button", { name: "Confirm manual update", exact: true })
        .click()
    })
    await expect
      .element(page.getByRole("alert"))
      .toHaveTextContent("the request may have reached the server")
    expect(
      screen.getByRole("button", { name: "Confirm manual update" })
    ).toBeDisabled()
    const dialog = screen.getByRole("dialog")
    expect(dialog.getBoundingClientRect().left).toBeGreaterThanOrEqual(0)
    expect(dialog.getBoundingClientRect().right).toBeLessThanOrEqual(width)
    await page.screenshot({
      path: `/private/tmp/loupe-updates-${width}-request-recovery.png`,
    })
    vi.mocked(platformUpdateAPI.getStatus).mockResolvedValue({
      ...available,
      deployment_running: true,
      deployment_status: "running",
      can_deploy: false,
    })
    await act(async () => {
      await page
        .getByRole("dialog")
        .getByRole("button", { name: "Refresh information", exact: true })
        .click()
    })
    await expect.element(page.getByRole("dialog")).not.toBeInTheDocument()
    await expect
      .element(page.getByText("Manual update running", { exact: true }))
      .toBeVisible()
    expect(
      screen.getByRole("button", { name: "Start manual update" })
    ).toBeDisabled()
    expect(platformUpdateAPI.deploy).toHaveBeenCalledTimes(1)
    expect(platformUpdateAPI.check).toHaveBeenCalledTimes(1)
    expect(platformUpdateAPI.getStatus).toHaveBeenCalledTimes(2)
  })
}

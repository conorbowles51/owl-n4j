import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { toast } from "sonner"
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
beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(platformUpdateAPI.getStatus).mockResolvedValue(available)
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
})
afterEach(() => {
  cleanup()
  client.clear()
})
function show() {
  return render(
    <QueryClientProvider client={client}>
      <PlatformUpdatesPage />
    </QueryClientProvider>
  )
}

describe("PlatformUpdatesPage investigator and administrator journeys", () => {
  it("explains the unavailable manual option without showing raw setup errors or claiming automatic failure", async () => {
    vi.mocked(platformUpdateAPI.getStatus).mockResolvedValue({
      ...available,
      configured: false,
      can_deploy: false,
      config_error: "sudo: synthetic service access denied",
    })
    show()
    await screen.findByText("Manual update unavailable")
    expect(
      screen.getByText(/Published improvements are deployed automatically/)
    ).toBeVisible()
    expect(
      screen.getByText(/This page does not report the progress or outcome/)
    ).toBeVisible()
    const raw = screen.getByText("sudo: synthetic service access denied")
    expect(raw).not.toBeVisible()
    expect(
      screen.getByRole("button", { name: "Start manual update" })
    ).toBeDisabled()
    fireEvent.click(screen.getByText("Technical details for administrators"))
    expect(raw).toBeVisible()
    expect(screen.getByText("Local checkout revision")).toBeVisible()
    expect(screen.getByText("synthetic-self-update.service")).toBeVisible()
    expect(platformUpdateAPI.deploy).not.toHaveBeenCalled()
  })

  it("recovers an information request failure with a read-only refresh", async () => {
    vi.mocked(platformUpdateAPI.getStatus).mockRejectedValueOnce(
      Error("internal synthetic diagnostic")
    )
    show()
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Update information could not be loaded"
    )
    expect(screen.getByText("Information unavailable")).toBeVisible()
    expect(screen.getByText("internal synthetic diagnostic")).not.toBeVisible()
    fireEvent.click(screen.getByRole("button", { name: "Refresh information" }))
    await screen.findByText("Manual update available")
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
    expect(platformUpdateAPI.getStatus).toHaveBeenCalledTimes(2)
    expect(platformUpdateAPI.check).not.toHaveBeenCalled()
    expect(platformUpdateAPI.deploy).not.toHaveBeenCalled()
  })

  it("requires explicit confirmation, preserves cancel, and shows the returned running state", async () => {
    vi.mocked(platformUpdateAPI.deploy).mockResolvedValue({
      ...available,
      deployment_running: true,
      deployment_status: "running",
      can_deploy: false,
    })
    show()
    await screen.findByText("Manual update available")
    fireEvent.click(screen.getByRole("button", { name: "Start manual update" }))
    const dialog = screen.getByRole("dialog")
    expect(within(dialog).getByText(/Save unfinished work/)).toBeVisible()
    expect(within(dialog).getByText("aaaaaaa")).not.toBeVisible()
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }))
    expect(platformUpdateAPI.deploy).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole("button", { name: "Start manual update" }))
    fireEvent.click(
      screen.getByRole("button", { name: "Confirm manual update" })
    )
    await screen.findByText("Manual update running")
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: "Start manual update" })
    ).toBeDisabled()
    expect(platformUpdateAPI.deploy).toHaveBeenCalledTimes(1)
  })

  it("does not repeat an uncertain update request and refreshes its result before allowing another", async () => {
    vi.mocked(platformUpdateAPI.deploy).mockRejectedValue(
      Error("sudo: synthetic connection lost")
    )
    show()
    await screen.findByText("Manual update available")
    fireEvent.click(screen.getByRole("button", { name: "Start manual update" }))
    fireEvent.click(
      screen.getByRole("button", { name: "Confirm manual update" })
    )
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "the request may have reached the server"
    )
    expect(
      screen.getByRole("button", { name: "Confirm manual update" })
    ).toBeDisabled()
    expect(toast.error).toHaveBeenCalledWith(
      expect.not.stringContaining("sudo")
    )
    vi.mocked(platformUpdateAPI.getStatus).mockResolvedValue({
      ...available,
      deployment_running: true,
      deployment_status: "running",
      can_deploy: false,
    })
    fireEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", {
        name: "Refresh information",
      })
    )
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    )
    expect(screen.getByText("Manual update running")).toBeVisible()
    expect(platformUpdateAPI.deploy).toHaveBeenCalledTimes(1)
  })

  it("keeps a failed check readable and permits a subsequent successful comparison", async () => {
    vi.mocked(platformUpdateAPI.check)
      .mockRejectedValueOnce(Error("fatal: synthetic remote unavailable"))
      .mockResolvedValue({
        ...available,
        can_deploy: false,
        update_available: false,
        remote_sha: available.local_sha,
        remote_short_sha: available.local_short_sha,
      })
    show()
    await screen.findByText("Manual update available")
    fireEvent.click(screen.getByRole("button", { name: "Check for updates" }))
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The manual update check could not be completed"
    )
    expect(
      screen.getByRole("button", { name: "Start manual update" })
    ).toBeDisabled()
    expect(
      screen.getByText("fatal: synthetic remote unavailable")
    ).not.toBeVisible()
    fireEvent.click(screen.getByRole("button", { name: "Check for updates" }))
    await screen.findByText("No manual update available")
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
    expect(platformUpdateAPI.deploy).not.toHaveBeenCalled()
  })
})

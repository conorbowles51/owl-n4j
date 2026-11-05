import type { ReactNode } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { logMatches, TASKS_SHOWN } from "../admin-rows"
import { BackgroundTasksPage } from "./BackgroundTasksPage"
import { SystemLogsPage } from "./SystemLogsPage"

vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))

const shown = (ui: ReactNode) =>
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{ui}</QueryClientProvider>)

const log = {
  timestamp: "2026-11-05T12:00:00Z", type: "case_management", origin: "backend", action: "Case opened",
  user: "a@b.c", success: false, error: "no such case",
}
const task = {
  id: "t1", task_type: "ingest", task_name: "Reading 3 files", owner: "a@b.c", status: "running",
  created_at: "2026-11-05T12:00:00Z", started_at: null, progress: { total: 4, completed: 1, failed: 0 }, error: null,
}

beforeEach(() => vi.mocked(fetchAPI).mockReset())
afterEach(cleanup)

describe("System Logs reads the server's route and row", () => {
  it("asks /api/system-logs and draws the action, who and the failure", async () => {
    vi.mocked(fetchAPI).mockResolvedValue({ logs: [log], total: 1 })
    shown(<SystemLogsPage />)
    expect(await screen.findByText(/Case opened/)).toBeTruthy()
    expect(screen.getByText(/no such case/)).toBeTruthy()
    expect(screen.getByText("failed")).toBeTruthy()
    expect(vi.mocked(fetchAPI).mock.calls[0]?.[0]).toMatch(/^\/api\/system-logs\?limit=\d+$/)
  })

  it("says so when the newest rows are not all the rows", async () => {
    vi.mocked(fetchAPI).mockResolvedValue({ logs: [log], total: 7421 })
    shown(<SystemLogsPage />)
    expect(await screen.findByText(/newest 1 of 7,421 entries/)).toBeTruthy()
  })

  it("shows a refusal, not an empty log", async () => {
    vi.mocked(fetchAPI).mockRejectedValue(new Error("Administrators only"))
    shown(<SystemLogsPage />)
    expect((await screen.findByRole("alert")).textContent).toContain("Administrators only")
    expect(screen.queryByText("No log entries")).toBeNull()
  })

  it("filters on what a row shows", () => {
    expect(logMatches(log, "SUCH")).toBe(true)
    expect(logMatches(log, "nothing here")).toBe(false)
  })
})

describe("Background Tasks reads the server's route and row", () => {
  it("asks for every person's tasks and draws name, owner and no Cancel", async () => {
    vi.mocked(fetchAPI).mockResolvedValue({ tasks: [task] })
    shown(<BackgroundTasksPage />)
    expect(await screen.findByText("Reading 3 files")).toBeTruthy()
    expect(screen.getByText("a@b.c")).toBeTruthy()
    expect(screen.getByText("1 running")).toBeTruthy()
    expect(screen.queryByRole("button", { name: /cancel/i })).toBeNull()
    expect(vi.mocked(fetchAPI).mock.calls[0]?.[0]).toBe(`/api/background-tasks?all_owners=true&limit=${TASKS_SHOWN}`)
  })

  it("says so at the row limit", async () => {
    vi.mocked(fetchAPI).mockResolvedValue({ tasks: Array.from({ length: TASKS_SHOWN }, (_, i) => ({ ...task, id: `t${i}` })) })
    shown(<BackgroundTasksPage />)
    expect(await screen.findByText(/older ones are not listed/)).toBeTruthy()
  })

  it("shows a refusal, not an empty list", async () => {
    vi.mocked(fetchAPI).mockRejectedValue(new Error("Administrators only"))
    shown(<BackgroundTasksPage />)
    expect((await screen.findByRole("alert")).textContent).toContain("Administrators only")
  })
})

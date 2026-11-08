import type { ReactNode } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { logMatches, TASKS_SHOWN } from "../admin-rows"
import { BackgroundTasksPage } from "./BackgroundTasksPage"
import { SystemLogsPage } from "./SystemLogsPage"
import { RUNNING_WORK_URL } from "./RunningWorkPanel"
import { useAuthStore } from "@/features/auth/hooks/use-auth"

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

beforeEach(() => {
  vi.mocked(fetchAPI).mockReset()
  useAuthStore.setState({ isAuthenticated: true, user: { username: "a", name: "Admin", role: "admin", global_role: "admin" } })
})

const nothingRunning = { scope: "all", tasks: [], stopped: [] }
/** The recorded-tasks answer for its route; the Running now route answers nothing running unless given. */
function answer(recorded: unknown, running: unknown = nothingRunning) {
  vi.mocked(fetchAPI).mockImplementation(async (url: string) => {
    if (url.startsWith(RUNNING_WORK_URL)) {
      if (typeof running === "function") return running(url)
      return running
    }
    if (recorded instanceof Error) throw recorded
    return recorded
  })
}
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
    answer({ tasks: [task] })
    shown(<BackgroundTasksPage />)
    expect(await screen.findByText("Reading 3 files")).toBeTruthy()
    expect(screen.getByText("a@b.c")).toBeTruthy()
    expect(screen.getByText("1 recorded running")).toBeTruthy()
    expect(screen.queryByRole("button", { name: /cancel/i })).toBeNull()
    expect(vi.mocked(fetchAPI).mock.calls.map((c) => c[0])).toContain(`/api/background-tasks?all_owners=true&limit=${TASKS_SHOWN}`)
  })

  it("says so at the row limit", async () => {
    answer({ tasks: Array.from({ length: TASKS_SHOWN }, (_, i) => ({ ...task, id: `t${i}` })) })
    shown(<BackgroundTasksPage />)
    expect(await screen.findByText(/older ones are not listed/)).toBeTruthy()
  })

  it("shows a refusal, not an empty list", async () => {
    answer(new Error("Administrators only"))
    shown(<BackgroundTasksPage />)
    expect((await screen.findByRole("alert")).textContent).toContain("Administrators only")
  })
})

const processing = {
  kind: "processing", id: "c1", case_id: "c1", case_title: "Verification", name: "Processing 3 files",
  status: "running", started_by: null, progress: { total: 3 },
}

describe("Stop on Background Tasks", () => {
  it("stops running work after a confirm and shows what finished and what did not", async () => {
    const summary = "Stopped by Admin. Of 3 files processing: 3 asked to stop."
    answer({ tasks: [] }, (url: string) =>
      url.endsWith("/stop") ? { status: "stopped", summary } : { scope: "all", tasks: [processing], stopped: [] })
    shown(<BackgroundTasksPage />)
    fireEvent.click(await screen.findByRole("button", { name: /^Stop$/ }))
    expect(screen.getByText(/Files already finished stay in the case/)).toBeTruthy()
    expect(vi.mocked(fetchAPI).mock.calls.some((c) => String(c[0]).endsWith("/stop"))).toBe(false)
    fireEvent.click(screen.getByRole("button", { name: "Stop now" }))
    expect((await screen.findByRole("status")).textContent).toBe(summary)
    const call = vi.mocked(fetchAPI).mock.calls.find((c) => String(c[0]).endsWith("/stop"))
    expect(call?.[0]).toBe(`${RUNNING_WORK_URL}/processing/c1/stop`)
    expect(call?.[1]).toMatchObject({ method: "POST" })
  })

  it("says plainly when the server refuses the stop", async () => {
    answer({ tasks: [] }, (url: string) => {
      if (url.endsWith("/stop")) throw new Error("Only an administrator or this case's owner can stop its work.")
      return { scope: "all", tasks: [processing], stopped: [] }
    })
    shown(<BackgroundTasksPage />)
    fireEvent.click(await screen.findByRole("button", { name: /^Stop$/ }))
    fireEvent.click(screen.getByRole("button", { name: "Stop now" }))
    expect((await screen.findByRole("status")).textContent).toContain("Not stopped: Only an administrator")
  })

  it("a case owner who is not an administrator sees only Running now, never every person's tasks", async () => {
    useAuthStore.setState({ isAuthenticated: true, user: { username: "o", name: "Owner", role: "user", global_role: "user" } })
    answer({ tasks: [task] }, { scope: "owned_cases", tasks: [processing], stopped: [
      { status: "stopped", name: "Whole-case export", summary: "Stopped by Owner. 4 of 10 items were written", stopped_at: "2026-11-08T20:00:00Z" },
    ] })
    shown(<BackgroundTasksPage />)
    expect(await screen.findByText("Processing 3 files")).toBeTruthy()
    expect(screen.getByText("Work in the cases you own")).toBeTruthy()
    expect(screen.getByText(/4 of 10 items were written/)).toBeTruthy()
    expect(vi.mocked(fetchAPI).mock.calls.map((c) => c[0])).not.toContain(`/api/background-tasks?all_owners=true&limit=${TASKS_SHOWN}`)
    expect(screen.queryByText("Reading 3 files")).toBeNull()
  })
})

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { ApiError, fetchAPI } from "@/lib/api-client"
import type { FlagPage, ProposalPage } from "../phone-registry"
import { PhoneRegistryPage } from "./PhoneRegistryPage"

vi.mock("@/lib/api-client", async () => {
  class ApiError extends Error {
    status: number
    constructor(message: string, status: number) {
      super(message)
      this.status = status
    }
  }
  return { fetchAPI: vi.fn(), ApiError }
})

const CASE = "cded78d0-0000-0000-0000-000000000001"
const EXT = "e0000000-0000-0000-0000-000000000002"

const flags: FlagPage = {
  total: 500,
  limit: 100,
  offset: 0,
  counts: { open: 500, acknowledged: 1, mapping_needed: 0, mapped: 0, dismissed: 0 },
  flags: [
    {
      id: 7, flag_kind: "new_set_value", registry_table: "set_values", severity: "info", state: "open",
      detail: { set: "ZzSet" }, raised_at: "2026-11-02T10:00:00Z", subject: { set: "ZzSet", value: "Zz1" },
      raised_by: { extraction_id: EXT, case_id: CASE, case_title: "Synthetic case", label: "Phone 1",
        link: `/cases/${CASE}/phones/${EXT}` },
      last_event: null,
    },
  ],
}

const proposals: ProposalPage = {
  total: 1,
  limit: 50,
  offset: 0,
  counts: { draft: 1, exported: 0, rejected: 0 },
  proposals: [
    {
      id: "p1", kind: "type", name: "Call", origin: "case_correction", state: "draft",
      created_at: "2026-11-03T10:00:00Z", model: null, case: { id: CASE, title: "Synthetic case" },
      rule_id: "Call.event_time", original: "TimeStamp", correction: "StartTime",
      correction_label: "When it happened is its start time",
      decided_by: { name: "Deciding Person", email: "d@x.test", reason: "the start is the event", at: "2026-11-03T10:00:00Z" },
      last_event: null, file_path: "backend/services/phone/mappings/data/type/Call.json",
    },
  ],
}

let client: QueryClient
const calls: { url: string; opts?: { method?: string; body?: unknown } }[] = []

function renderPage() {
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <PhoneRegistryPage />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

beforeEach(() => {
  vi.resetAllMocks()
  calls.length = 0
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  vi.mocked(fetchAPI).mockImplementation(async (url: string, opts?: unknown) => {
    calls.push({ url, opts: opts as { method?: string; body?: unknown } })
    if (url.startsWith("/api/phones/registry/flags?")) return flags
    if (url.startsWith("/api/phones/registry/proposals?")) return proposals
    if (url.endsWith("/export")) return { kind: "type", name: "Call", status: "draft" }
    return { ok: true }
  })
})
afterEach(cleanup)

describe("PhoneRegistryPage", () => {
  it("shows true totals per state and the range of the page, with the raising phone linked", async () => {
    renderPage()
    expect(await screen.findByText("Showing 1 to 1 of 500")).toBeTruthy()
    expect(screen.getByRole("button", { name: "Open (500)" })).toBeTruthy()
    expect(screen.getByRole("button", { name: "All (501)" })).toBeTruthy()
    const row = screen.getByTestId("flag-7")
    expect(within(row).getByText("ZzSet: Zz1")).toBeTruthy()
    expect(within(row).getByRole("link").getAttribute("href")).toBe(`/cases/${CASE}/phones/${EXT}`)
    expect(calls[0].url).toBe("/api/phones/registry/flags?state=open&limit=100&offset=0")
  })

  it("asks for a reason before a flag is dismissed and sends it", async () => {
    renderPage()
    const row = await screen.findByTestId("flag-7")
    fireEvent.click(within(row).getByRole("button", { name: "Dismiss" }))
    const confirm = within(row).getAllByRole("button", { name: "Dismiss" }).at(-1)!
    expect((confirm as HTMLButtonElement).disabled).toBe(true)
    fireEvent.change(within(row).getByLabelText("Reason"), { target: { value: "known vocabulary" } })
    expect((confirm as HTMLButtonElement).disabled).toBe(false)
    fireEvent.click(confirm)
    await waitFor(() => expect(calls.some((c) => c.url === "/api/phones/registry/flags/7/transition")).toBe(true))
    const post = calls.find((c) => c.url === "/api/phones/registry/flags/7/transition")!
    expect(post.opts).toMatchObject({ method: "POST", body: { to: "dismissed", reason: "known vocabulary" } })
  })

  it("tells a non-admin the page is for administrators", async () => {
    vi.mocked(fetchAPI).mockRejectedValue(new ApiError("Forbidden", 403))
    renderPage()
    expect(await screen.findByText("Only an administrator can see the phone registry.")).toBeTruthy()
  })

  it("lists proposals with the original reading beside the correction, the deciding person, Reject and Download", async () => {
    const created = vi.fn(() => "blob:x")
    Object.assign(URL, { createObjectURL: created, revokeObjectURL: vi.fn() })
    renderPage()
    fireEvent.mouseDown(await screen.findByRole("tab", { name: "Proposals" }), { button: 0 })
    const row = await screen.findByTestId("proposal-p1")
    expect(within(row).getByText("TimeStamp")).toBeTruthy()
    expect(within(row).getByText("When it happened is its start time")).toBeTruthy()
    expect(within(row).getByText(/Deciding Person/)).toBeTruthy()
    expect(within(row).getByRole("link", { name: "Synthetic case" })).toBeTruthy()
    expect(screen.getByText("Showing 1 to 1 of 1")).toBeTruthy()
    fireEvent.click(within(row).getByRole("button", { name: "Download file" }))
    await waitFor(() => expect(created).toHaveBeenCalled())
    expect(calls.some((c) => c.url === "/api/phones/registry/proposals/p1/export")).toBe(true)
    fireEvent.click(within(row).getByRole("button", { name: "Reject" }))
    fireEvent.change(within(row).getByLabelText("Reason"), { target: { value: "right for every case" } })
    fireEvent.click(within(row).getAllByRole("button", { name: "Reject" }).at(-1)!)
    await waitFor(() => expect(calls.some((c) => c.url === "/api/phones/registry/proposals/p1/reject")).toBe(true))
    expect(calls.find((c) => c.url.endsWith("/reject"))!.opts).toMatchObject({ method: "POST", body: { reason: "right for every case" } })
  })
})

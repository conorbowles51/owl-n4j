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

  it("tells a non-admin the page is for administrators at once, without retrying the refusal", async () => {
    client = new QueryClient() // the app's default retries, so a retried 403 would delay the message by seconds
    vi.mocked(fetchAPI).mockRejectedValue(new ApiError("Forbidden", 403))
    renderPage()
    expect(await screen.findByText("Only an administrator can see the phone registry.", {}, { timeout: 900 })).toBeTruthy()
    expect(vi.mocked(fetchAPI).mock.calls.filter(([u]) => String(u).startsWith("/api/phones/registry/flags")).length).toBe(1)
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

  it("offers Draft a mapping on a flag waiting for a mapping and sends the set it is about", async () => {
    const waiting: FlagPage = {
      ...flags,
      flags: [{ ...flags.flags[0], id: 8, state: "mapping_needed" }],
    }
    vi.mocked(fetchAPI).mockImplementation(async (url: string, opts?: unknown) => {
      calls.push({ url, opts: opts as { method?: string; body?: unknown } })
      if (url.startsWith("/api/phones/registry/flags?")) return waiting
      if (url === "/api/phones/registry/mapping-drafts") return { id: "r1", status: "queued" }
      return { ok: true }
    })
    renderPage()
    const row = await screen.findByTestId("flag-8")
    fireEvent.click(within(row).getByRole("button", { name: "Draft a mapping for ZzSet" }))
    await waitFor(() => expect(calls.some((c) => c.url === "/api/phones/registry/mapping-drafts")).toBe(true))
    expect(calls.find((c) => c.url === "/api/phones/registry/mapping-drafts")!.opts)
      .toMatchObject({ method: "POST", body: { type_name: "ZzSet" } })
    expect(await within(row).findByText(/arrives in Proposals/)).toBeTruthy()
  })

  it("shows an open flag without a draft button (only a flag waiting for a mapping is drafted)", async () => {
    renderPage()
    const row = await screen.findByTestId("flag-7")
    expect(within(row).queryByRole("button", { name: /Draft a mapping/ })).toBeNull()
  })

  it("names the model on an AI draft proposal and says it is not reviewed", async () => {
    const ai: ProposalPage = {
      ...proposals,
      proposals: [{ ...proposals.proposals[0], id: "p2", origin: "ai_draft", model: "deepseek-v4-pro", case: null,
        rule_id: null, original: null, correction: null, correction_label: null, decided_by: null }],
    }
    vi.mocked(fetchAPI).mockImplementation(async (url: string) => {
      if (url.startsWith("/api/phones/registry/flags?")) return flags
      if (url.startsWith("/api/phones/registry/proposals?")) return ai
      return { ok: true }
    })
    renderPage()
    fireEvent.mouseDown(await screen.findByRole("tab", { name: "Proposals" }), { button: 0 })
    const row = await screen.findByTestId("proposal-p2")
    expect(within(row).getByText("AI draft")).toBeTruthy()
    expect(within(row).getByText("Drafted by deepseek-v4-pro; not reviewed")).toBeTruthy()
    expect(within(row).getByRole("button", { name: "Download file" })).toBeTruthy()
    expect(within(row).getByRole("button", { name: "Reject" })).toBeTruthy()
  })

  it("AI drafts: picks a type, starts a draft, and lists runs with model, time, cost and the reason a draft failed", async () => {
    const page = {
      total: 2,
      runs: [
        { id: "r1", kind: "type", name: "Call", status: "drafted", provider: "deepseek", model: "deepseek-v4-pro",
          input_summary: {}, proposal_id: "p9", error: null, seconds: 134, prompt_tokens: 1, completion_tokens: 2,
          cost_usd: 0.0123, requested_by: "Admin Person", created_at: "2026-11-04T10:00:00Z", finished_at: null },
        { id: "r2", kind: "attribution", name: "ZzSet", status: "invalid", provider: "deepseek",
          model: "deepseek-v4-pro", input_summary: {}, proposal_id: "p10", error: "Zz is not a value of ZzSet",
          seconds: 40, prompt_tokens: 1, completion_tokens: 2, cost_usd: null, requested_by: "Admin Person",
          created_at: "2026-11-04T10:00:00Z", finished_at: null },
      ],
      draftable: { types: [{ name: "Call", kind: "type", records_observed: 5341 }],
        named_sets: [{ name: "ZzSet", kind: "attribution", records_observed: 3 }], total: 2 },
    }
    vi.mocked(fetchAPI).mockImplementation(async (url: string, opts?: unknown) => {
      calls.push({ url, opts: opts as { method?: string; body?: unknown } })
      if (url.startsWith("/api/phones/registry/flags?")) return flags
      if (url.startsWith("/api/phones/registry/mapping-drafts?")) return page
      if (url === "/api/phones/registry/mapping-drafts") return { id: "r3", status: "queued" }
      return { ok: true }
    })
    renderPage()
    fireEvent.mouseDown(await screen.findByRole("tab", { name: "AI drafts" }), { button: 0 })
    const r1 = await screen.findByTestId("draft-r1")
    expect(within(r1).getByText("deepseek-v4-pro · 2 min 14 s · $0.0123")).toBeTruthy()
    expect(within(r1).getByText("Drafted: waiting in Proposals")).toBeTruthy()
    const r2 = screen.getByTestId("draft-r2")
    expect(within(r2).getByText("Zz is not a value of ZzSet")).toBeTruthy()
    expect(screen.getByText("Latest 2 of 2 drafts")).toBeTruthy()
    expect(screen.getByText(/never sees a case/)).toBeTruthy()
    fireEvent.change(screen.getByLabelText("Record type or list"), { target: { value: "Call" } })
    fireEvent.click(screen.getByRole("button", { name: "Draft a mapping" }))
    await waitFor(() => expect(calls.some((c) => c.url === "/api/phones/registry/mapping-drafts")).toBe(true))
    expect(calls.find((c) => c.url === "/api/phones/registry/mapping-drafts")!.opts)
      .toMatchObject({ method: "POST", body: { type_name: "Call" } })
  })
})

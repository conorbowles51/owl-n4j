import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { useEffect } from "react"
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { TooltipProvider } from "@/components/ui/tooltip"
import { dispatchKey, resetKeymapForTest } from "@/lib/keymap"

/** Conversations (03 section 6, 07 J-12, J-13, D-38) with the server and the list stubbed. Synthetic data only. */
const api = vi.hoisted(() => ({
  getPhones: vi.fn(),
  getSettings: vi.fn(),
  getThreads: vi.fn(),
  getParticipants: vi.fn(),
  markReviewed: vi.fn(),
  undoReviewed: vi.fn(),
  markNotACopy: vi.fn(),
  freezeSelection: vi.fn(),
}))
vi.mock("@/features/phones/api", async (orig) => ({ ...(await orig<object>()), ...api }))
vi.mock("@/features/cases/hooks/use-cases", () => ({ useCase: () => ({ data: { title: "Synthetic case" } }) }))
vi.mock("@/features/phones/hooks/use-collect", () => ({
  useCollectTargets: () => ({ data: [] }),
  useUsedIn: () => ({ usedIn: {}, refresh: vi.fn() }),
}))
const streamFilters = vi.hoisted(() => [] as unknown[])
vi.mock("@/features/phones/hooks/use-stream", () => ({
  useStream: (f: unknown) => {
    streamFilters.push(f)
    return { status: "idle", error: null, index: null, segments: [], count: 0, total: 0, notice: null, item: () => ({ type: "header", segment: 0 }), ensure: vi.fn(), retry: vi.fn(), reload: vi.fn(), positionOf: () => null, allRows: async () => [], setFocused: vi.fn() }
  },
}))
const mounts = vi.hoisted(() => ({ n: 0 }))
vi.mock("@/features/phones/components/StreamList", async () => {
  const { useEffect } = await import("react")
  return {
    StreamList: () => {
      useEffect(() => {
        mounts.n += 1
      }, [])
      return <div data-testid="stream" />
    },
  }
})
vi.mock("@/lib/ux-events", () => ({ trackUx: vi.fn() }))

import ConversationsPage from "./ConversationsPage"

const label = (name: string) => ({ identity_key: `phone:${name}`, name, name_basis: "contact_on_this_phone", identifier: null, is_owner: false, owner_basis: null, case_names: [] })
const thread = (key: string, title: string, reviewed = false) => ({
  thread_key: key, phone: { extraction_id: "e1", label: "C1" }, app: "SyntheticApp", chat_type: null, thread_kind: "chat", title,
  participants: [label(title)], participant_count: 2, first_instant: null, last_instant: null, last_full: "", event_count: 3,
  event_count_total: 3, deleted_count: 0, has_unreadable: false,
  review: reviewed ? { by: "Synthetic Reviewer", at: "2026-11-02T09:00:00Z", record_count: 3, added_since: 0, words: "Reviewed by Synthetic Reviewer on Mon, Nov 2, 2026 (3 messages)" } : null,
})

const threadOptions = async () => within(await screen.findByRole("listbox", { name: /^Threads/ })).findAllByRole("option")

const seen = { search: "" }
function Where() {
  const search = useLocation().search
  useEffect(() => {
    seen.search = search
  }, [search])
  return null
}

function page(entry = "/cases/case-1/conversations") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <TooltipProvider>
        <MemoryRouter initialEntries={[entry]}>
          <Routes>
            <Route path="/cases/:id/conversations" element={<><ConversationsPage /><Where /></>} />
          </Routes>
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  )
}

describe("Conversations", () => {
  beforeEach(() => {
    resetKeymapForTest()
    streamFilters.length = 0
    api.getPhones.mockResolvedValue({ case_id: "case-1", phones: [{ extraction_id: "e1", label: "C1" }] })
    api.getSettings.mockResolvedValue({ case_id: "case-1", time_zone: null, effective: { name: "UTC", basis: "default", note: null }, updated_at: null, updated_by: null })
    api.getThreads.mockResolvedValue({ case_id: "case-1", snapshot: "s", complete: true, limits: [], counts: { threads: 2, threads_total: 2, reviewed: 0, not_reviewed: 2 }, items: [thread("t1", "Synthetic A"), thread("t2", "Synthetic B")], sort: "recent" })
    api.markReviewed.mockResolvedValue({ thread_key: "t1", review: { by: "x", at: "y", record_count: 3, added_since: 0, words: "w" } })
    api.undoReviewed.mockResolvedValue({ thread_key: "t1", restored: false })
  })
  afterEach(() => vi.clearAllMocks())

  it("opens the first thread on arrival so the keys act at once (D-38), in the URL", async () => {
    page()
    await waitFor(() => expect(seen.search).toContain("thread=t1"))
    const options = await threadOptions()
    expect(options[0]).toHaveAttribute("aria-selected", "true")
    expect(streamFilters.some((f) => (f as { threads?: string[] } | null)?.threads?.[0] === "t1")).toBe(true)
  })

  it("states what is not yet reviewed, and m marks the open thread with Undo (07 J-13)", async () => {
    page()
    await screen.findByText("Not yet reviewed: 2 of 2 threads")
    await waitFor(() => expect(seen.search).toContain("thread=t1"))
    dispatchKey(new KeyboardEvent("keydown", { key: "m" }))
    await waitFor(() => expect(api.markReviewed).toHaveBeenCalledWith("case-1", "t1", expect.any(Object)))
    fireEvent.click(await screen.findByRole("button", { name: "Undo" }))
    await waitFor(() => expect(api.undoReviewed).toHaveBeenCalledWith("case-1", "t1"))
  })

  it("quick-find narrows the threads and says how many are shown", async () => {
    page()
    await threadOptions()
    fireEvent.change(screen.getByLabelText("Find a thread"), { target: { value: "synthetic b" } })
    expect(await threadOptions()).toHaveLength(1)
    expect(screen.getByText("Showing 1 of 2 threads")).toBeInTheDocument()
  })

  it("a person link opens the people tab and reads that person's messages", async () => {
    api.getParticipants.mockResolvedValue({ case_id: "case-1", snapshot: "s", complete: true, limits: [], counts: { participants: 1 }, items: [{ label: label("Synthetic A"), events: 3, first_instant: null, last_instant: null, phones: ["C1"], apps: ["SyntheticApp"] }] })
    page("/cases/case-1/conversations?tab=people&people=phone%3ASynthetic%20A")
    const option = await screen.findByRole("option", { name: /Synthetic A/ })
    expect(option).toHaveAttribute("aria-selected", "true")
    expect(seen.search).not.toContain("thread=")
    expect(streamFilters.some((f) => (f as { participants?: string[] } | null)?.participants?.[0] === "phone:Synthetic A")).toBe(true)
  })

  it("a case with no phone says so", async () => {
    api.getPhones.mockResolvedValue({ case_id: "case-1", phones: [] })
    page()
    await screen.findByText(/This case has no phone yet\./)
  })

  it("a new thread starts with nothing selected: the list is a new one (review of 03-3)", async () => {
    page()
    await waitFor(() => expect(seen.search).toContain("thread=t1"))
    const before = mounts.n
    fireEvent.click((await threadOptions())[1])
    await waitFor(() => expect(seen.search).toContain("thread=t2"))
    await waitFor(() => expect(mounts.n).toBeGreaterThan(before))
  })
})

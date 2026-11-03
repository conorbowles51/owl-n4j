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
  streamLocate: vi.fn(),
  getLinkedIdentities: vi.fn(),
  streamIndex: vi.fn(),
  getSelection: vi.fn(),
  translateThread: vi.fn(),
}))
vi.mock("@/features/phones/api", async (orig) => ({ ...(await orig<object>()), ...api }))
vi.mock("@/features/cases/hooks/use-cases", () => ({ useCase: () => ({ data: { title: "Synthetic case" } }) }))
vi.mock("@/features/phones/hooks/use-collect", () => ({
  useCollectTargets: () => ({ data: [] }),
  useUsedIn: () => ({ usedIn: {}, refresh: vi.fn() }),
}))
const streamFilters = vi.hoisted(() => [] as unknown[])
const streamState = vi.hoisted(() => ({ index: null as unknown }))
const threadMatches = vi.hoisted(() => ({ value: { isLoading: false, data: undefined as unknown } }))
vi.mock("./use-thread-matches", () => ({ useThreadMatches: () => threadMatches.value }))
const listProps = vi.hoisted(() => ({ last: null as null | { highlight?: unknown; jumpTo?: unknown } }))
vi.mock("@/features/phones/hooks/use-stream", () => ({
  useStream: (f: unknown) => {
    streamFilters.push(f)
    return { status: "idle", error: null, index: streamState.index, segments: [], count: 0, total: 0, notice: null, item: () => ({ type: "header", segment: 0 }), ensure: vi.fn(), retry: vi.fn(), reload: vi.fn(), positionOf: () => null, allRows: async () => [], checkSnapshot: async () => true, setFocused: vi.fn() }
  },
}))
const mounts = vi.hoisted(() => ({ n: 0 }))
vi.mock("@/features/phones/components/StreamList", async () => {
  const { useEffect } = await import("react")
  return {
    StreamList: (props: { highlight?: unknown; jumpTo?: unknown }) => {
      listProps.last = props
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
  afterEach(() => {
    vi.clearAllMocks()
    streamState.index = null
    threadMatches.value = { isLoading: false, data: undefined }
  })

  it("a search hit shows the whole thread, says how many messages matched, marks them and steps through them (S-8)", async () => {
    streamState.index = { snapshot: "s", zone: { label: "UTC" }, items: [], counts: {} }
    threadMatches.value = { isLoading: false, data: { total: 3, events: ["v1", "v2", "v3"] } }
    api.streamLocate.mockResolvedValue({ day: "2023-03-14", offset: 4 })
    page("/cases/case-1/conversations?thread=t1&at=v2&hl=jose")
    expect(await screen.findByText("Showing the whole conversation. Your search matched 3 messages here.")).toBeInTheDocument()
    await waitFor(() => expect(api.streamLocate).toHaveBeenCalledWith(expect.anything(), "s", "v2"))
    expect(await screen.findByText("Match 2 of 3")).toBeInTheDocument()
    expect(listProps.last?.highlight).toEqual({ query: "jose", exact: false })
    await waitFor(() => expect(listProps.last?.jumpTo).toMatchObject({ day: "2023-03-14", offset: 4 }))
    fireEvent.click(screen.getByRole("button", { name: "Next match" }))
    await waitFor(() => expect(api.streamLocate).toHaveBeenCalledWith(expect.anything(), "s", "v3"))
    expect(await screen.findByText("Match 3 of 3")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Next match" }))
    expect(await screen.findByText("Match 1 of 3")).toBeInTheDocument()  // wraps round
    expect(screen.getByRole("button", { name: "Back to results" })).toBeInTheDocument()
  })

  it("a chosen person reads on N of M phones, with Between A and B, All channels and the other-numbers switch (07 J-3)", async () => {
    api.getPhones.mockResolvedValue({ case_id: "case-1", phones: [{ extraction_id: "e1", label: "C1" }, { extraction_id: "e2", label: "C2" }, { extraction_id: "e3", label: "C3" }] })
    api.getParticipants.mockResolvedValue({ case_id: "case-1", snapshot: "s", complete: true, limits: [], counts: {}, items: [{ label: label("Synthetic A"), events: 4, first_instant: null, last_instant: null, phones: ["C1", "C3"], apps: [] }] })
    api.getLinkedIdentities.mockResolvedValue({ others: ["phone:+12025550199"], numbers: 1, accounts: 0 })
    api.streamIndex.mockResolvedValue({ counts: { events: 9 } })
    streamState.index = { snapshot: "s", zone: { label: "UTC" }, items: [], counts: { events: 5, messages: 4, calls: 1, phones: 2 } }
    page("/cases/case-1/conversations?tab=people&people=phone:Synthetic%20A&mode=between")
    const scope = await screen.findByRole("region", { name: "Scope" })
    expect(await within(scope).findByText("Synthetic A (no identifier recorded) (2 numbers, 0 accounts) on 2 of 3 phones")).toBeInTheDocument()
    expect(within(scope).getByRole("button", { name: "Between A and B" })).toHaveAttribute("aria-pressed", "true")
    expect(within(scope).getByText("4 messages and 1 call between Synthetic A (no identifier recorded) and the owner of each phone on 2 phones")).toBeInTheDocument()
    const sw = within(scope).getByRole("switch", { name: "Include this person's other numbers and accounts" })
    expect(sw).toHaveAttribute("aria-checked", "false")
    expect(await within(scope).findByText("Include 1 more number or account (+4 messages).")).toBeInTheDocument()
    expect(streamFilters.some((f) => JSON.stringify((f as { participants?: string[] } | null)?.participants) === JSON.stringify(["phone:Synthetic A", "owner:this-phone"]))).toBe(true)
    fireEvent.click(within(scope).getByRole("button", { name: "All channels" }))
    await waitFor(() => expect(seen.search).toContain("channels=all"))
  })

  it("says in the page header when a saved selection is shown, with its frozen totals", async () => {
    api.getSelection.mockResolvedValue({ id: "s1", words: "Synthetic selection", record_count: 3, event_count: 2, created_at: null, replaced: null })
    page("/cases/case-1/conversations?selection=s1")
    const line = await screen.findByTestId("saved-selection")
    await waitFor(() => expect(line.textContent).toContain("Synthetic selection"))
    expect(line.closest("header")?.textContent).toContain("Conversations")
    await threadOptions()
    expect(seen.search).not.toContain("thread=")
    expect(streamFilters.at(-1)).toMatchObject({ selection: "s1" })
    expect((streamFilters.at(-1) as { threads?: string[] }).threads ?? []).toEqual([])
  })

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

  it("Translate this conversation queues its messages on the server and states the counts, left out by reason (05 17.5)", async () => {
    api.translateThread.mockResolvedValue({ in_conversation: 3, queued: 2, left_out: { no_text: 1, already_translated: 0, already_waiting: 0 } })
    page()
    await waitFor(() => expect(seen.search).toContain("thread=t1"))
    fireEvent.click(await screen.findByRole("button", { name: "Translate this conversation" }))
    await waitFor(() => expect(api.translateThread).toHaveBeenCalledWith("case-1", "t1"))
    expect(await screen.findByTestId("translate-note")).toHaveTextContent(
      "2 messages of 3 queued for translation on this server; nothing is sent anywhere. Left out: 1 with no text.",
    )
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

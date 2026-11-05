import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { useEffect } from "react"
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom"
import { act } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { useNotebookStore } from "@/features/notebook/notebook.store"
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
  saveView: vi.fn(),
  getSavedView: vi.fn(),
  getReaderSettings: vi.fn(),
  saveReaderSettings: vi.fn(),
}))
const screenWide = vi.hoisted(() => ({ value: true }))
vi.mock("@/hooks/use-media-query", () => ({ useMediaQuery: () => screenWide.value }))
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
const listProps = vi.hoisted(() => ({ last: null as null | { highlight?: unknown; jumpTo?: unknown; density?: unknown; filterWords?: string; onGoToOriginal?: (t: unknown, r: unknown) => void } }))
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

import { StaleSnapshotError } from "@/features/phones/api"
import { ApiError } from "@/lib/api-client"
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
    sessionStorage.clear()
    streamFilters.length = 0
    api.getPhones.mockResolvedValue({ case_id: "case-1", phones: [{ extraction_id: "e1", label: "C1" }] })
    api.getSettings.mockResolvedValue({ case_id: "case-1", time_zone: null, effective: { name: "UTC", basis: "default", note: null }, updated_at: null, updated_by: null })
    api.getThreads.mockResolvedValue({ case_id: "case-1", snapshot: "s", complete: true, limits: [], counts: { threads: 2, threads_total: 2, reviewed: 0, not_reviewed: 2 }, items: [thread("t1", "Synthetic A"), thread("t2", "Synthetic B")], sort: "recent" })
    api.markReviewed.mockResolvedValue({ thread_key: "t1", review: { by: "x", at: "y", record_count: 3, added_since: 0, words: "w" } })
    api.undoReviewed.mockResolvedValue({ thread_key: "t1", restored: false })
  })
  afterEach(() => {
    vi.clearAllMocks()
    screenWide.value = true
    streamState.index = null
    threadMatches.value = { isLoading: false, data: undefined }
  })

  it("sets a filter into the URL, shows it as a removable chip and says the true total over every conversation (03 6.4)", async () => {
    api.streamIndex.mockResolvedValue({ snapshot: "s", counts: { events: 1234 }, no_time_count: 7, items: [], zone: { label: "UTC" } })
    page("/cases/case-1/conversations?thread=t1&directions=outgoing&from=2023-03-01")
    expect(await screen.findByText("Outgoing")).toBeInTheDocument()
    await waitFor(() => expect(screen.getByTestId("filter-total")).toHaveTextContent("1,234 messages and calls match in 2 of 2 conversations."))
    expect(await screen.findByText(/7 with no time are included/)).toBeInTheDocument()
    expect(screen.queryByText("Everything on every phone in this case")).not.toBeInTheDocument()
    expect(screen.getByTestId("filter-zone")).toHaveTextContent("Days in UTC")
    expect(listProps.last?.filterWords).toContain("Outgoing, From 2023-03-01")
    fireEvent.click(screen.getByRole("button", { name: "Remove Outgoing" }))
    await waitFor(() => expect(seen.search).not.toContain("directions"))
    expect(seen.search).toContain("from=2023-03-01")
    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }))
    await waitFor(() => expect(seen.search).toBe("?thread=t1"))
  })

  it("keeps both of two filters chosen before the page has drawn the first", async () => {
    page("/cases/case-1/conversations?thread=t1")
    await threadOptions()
    act(() => {
      fireEvent.change(screen.getByLabelText("Attachment"), { target: { value: "only" } })
      fireEvent.click(screen.getByLabelText("Exact characters"))
    })
    await waitFor(() => expect(seen.search).toContain("exact=1"))
    expect(seen.search).toContain("attachment=only")
  })

  it("moves off an open thread a filter has emptied, and says when nothing matches", async () => {
    api.streamIndex.mockResolvedValue({ snapshot: "s", counts: { events: 3 }, no_time_count: 0, items: [], zone: { label: "UTC" } })
    page("/cases/case-1/conversations?thread=gone&apps=SyntheticApp")
    await waitFor(() => expect(seen.search).toContain("thread=t1"))
    api.getThreads.mockResolvedValue({ case_id: "case-1", snapshot: "s", complete: true, limits: [], counts: { threads: 0, threads_total: 2, reviewed: 0, not_reviewed: 0 }, items: [], sort: "recent" })
    fireEvent.change(screen.getByLabelText("Attachment"), { target: { value: "only" } })
    expect(await screen.findByText("No conversation matches these filters.")).toBeInTheDocument()
    expect(await screen.findByTestId("thread-count")).toHaveTextContent("0 of 2 threads have messages matching these filters")
  })

  it("stays on an open thread that is not listed when no filter is set", async () => {
    page("/cases/case-1/conversations?thread=gone")
    await threadOptions()
    expect(seen.search).toContain("thread=gone")
  })

  it("collapses the thread list to a rail below 1440 px and back when a thread is picked (07 4.3)", async () => {
    screenWide.value = false
    page("/cases/case-1/conversations?thread=t1")
    const rail = await screen.findByRole("button", { name: "Threads (2)" })
    expect(screen.queryByRole("listbox", { name: /^Threads/ })).not.toBeInTheDocument()
    fireEvent.click(rail)
    fireEvent.click((await threadOptions())[1])
    expect(await screen.findByRole("button", { name: "Threads (2)" })).toBeInTheDocument()
    await waitFor(() => expect(seen.search).toContain("thread=t2"))
  })

  it("reads the person's saved density and saves a new choice (07 4.4)", async () => {
    api.getReaderSettings.mockResolvedValue({ stream_density: "compact" })
    api.saveReaderSettings.mockResolvedValue({ stream_density: "comfortable" })
    page("/cases/case-1/conversations?thread=t1")
    await waitFor(() => expect(listProps.last?.density).toBe("compact"))
    fireEvent.change(screen.getByLabelText("Density"), { target: { value: "comfortable" } })
    await waitFor(() => expect(api.saveReaderSettings.mock.calls[0][0]).toBe("comfortable"))
    await waitFor(() => expect(listProps.last?.density).toBe("comfortable"))
  })

  it("goes to a reply's original in place, or to its own conversation with the filters cleared, and says so", async () => {
    streamState.index = { snapshot: "s", zone: { label: "UTC" }, items: [], counts: {} }
    api.streamIndex.mockResolvedValue({ snapshot: "s", counts: { events: 1 }, no_time_count: 0, items: [], zone: { label: "UTC" } })
    api.streamLocate.mockResolvedValue({ day: "2023-03-14", offset: 2 })
    page("/cases/case-1/conversations?thread=t1&directions=outgoing")
    await threadOptions()
    const row = { phone: { extraction_id: "e1", label: "C1" } }
    await act(async () => listProps.last!.onGoToOriginal!({ event_uid: "v9", thread_key: "t2" }, row))
    await waitFor(() => expect(listProps.last?.jumpTo).toMatchObject({ day: "2023-03-14", offset: 2 }))
    expect(seen.search).toContain("thread=t1")
    api.streamLocate.mockRejectedValue(new ApiError("not in this list", 404))
    await act(async () => listProps.last!.onGoToOriginal!({ event_uid: "v9", thread_key: "t2" }, row))
    await waitFor(() => expect(seen.search).toContain("thread=t2"))
    expect(seen.search).toContain("at=v9")
    expect(seen.search).not.toContain("directions")
    expect(screen.getByTestId("original-note")).toHaveTextContent("shown in its own conversation with the filters cleared")
  })

  it("arrives at the message once the new list's index is in, and again after going Back", async () => {
    streamState.index = { snapshot: "old", zone: { label: "UTC" }, items: [], counts: {} }
    api.streamLocate.mockRejectedValueOnce(new StaleSnapshotError())
    api.streamLocate.mockResolvedValue({ day: "2023-03-14", offset: 2 })
    const view = page("/cases/case-1/conversations?thread=t1&at=v9")
    await waitFor(() => expect(api.streamLocate).toHaveBeenCalledTimes(1))
    streamState.index = { snapshot: "new", zone: { label: "UTC" }, items: [], counts: {} }
    fireEvent.click((await threadOptions())[0])
    await waitFor(() => expect(api.streamLocate).toHaveBeenLastCalledWith(expect.anything(), "new", "v9"))
    await waitFor(() => expect(listProps.last?.jumpTo).toMatchObject({ offset: 2 }))
    view.unmount()
  })

  it("keeps the view and every filter when finding the original fails for another reason", async () => {
    streamState.index = { snapshot: "s", zone: { label: "UTC" }, items: [], counts: {} }
    api.streamIndex.mockResolvedValue({ snapshot: "s", counts: { events: 1 }, no_time_count: 0, items: [], zone: { label: "UTC" } })
    api.streamLocate.mockRejectedValue(new Error("the network failed"))
    page("/cases/case-1/conversations?thread=t1&directions=outgoing")
    await threadOptions()
    await act(async () => listProps.last!.onGoToOriginal!({ event_uid: "v9", thread_key: "t2" }, { phone: { extraction_id: "e1", label: "C1" } }))
    expect(seen.search).toContain("directions=outgoing")
    expect(seen.search).toContain("thread=t1")
    expect(screen.getByTestId("original-note")).toBeInTheDocument()
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

  it("Save this view keeps the filter and where it was saved from in a Workspace note; a saved view states the count then and now (07 section 6)", async () => {
    streamState.index = { snapshot: "s", zone: { label: "UTC" }, items: [], counts: {} }
    api.saveView.mockResolvedValue({ id: "v1", entry_id: "n1", event_count: 9, words: "w" })
    page()
    await waitFor(() => expect(seen.search).toContain("thread=t1"))
    fireEvent.click(await screen.findByRole("button", { name: "Save this view" }))
    await waitFor(() => expect(api.saveView).toHaveBeenCalled())
    const [filter, where] = api.saveView.mock.calls[0]
    expect(filter).toMatchObject({ case_id: "case-1" })
    expect(where).toMatch(/^\/cases\/case-1\/conversations\?.*thread=t1/)
    expect(await screen.findByText(/Saved as a Workspace note \(9 messages now\)/)).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Open the note" })).toHaveAttribute("href", "/cases/case-1/workspace?view=casework&entry=n1")
  })

  it("a saved view opened from its note says the count when saved and now", async () => {
    api.getSavedView.mockResolvedValue({ id: "v1", words: "w", location: "/cases/case-1/conversations?thread=t1", event_count_then: 3, event_count_now: 5, created_at: null, sentence: 'Saved view "Synthetic view": 3 messages when saved on November 4, 2026; 5 now.', replaced: null })
    page("/cases/case-1/conversations?thread=t1&saved_view=v1")
    await waitFor(() => expect(screen.getByTestId("saved-view")).toHaveTextContent('Saved view "Synthetic view": 3 messages when saved on November 4, 2026; 5 now. The list below is the view re-run now.'))
    expect(api.getSavedView).toHaveBeenCalledWith("case-1", "v1")
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

  it("g opens Go to date beside its visible button (03 section 3.9, D-27)", async () => {
    streamState.index = { snapshot: "s", zone: { label: "UTC" }, items: [{ day: "2023-03-10", count: 2, offsets: "", header: "", zone_label: "UTC" }], counts: {} }
    page()
    await waitFor(() => expect(seen.search).toContain("thread=t1"))
    expect(await screen.findByRole("button", { name: /Go to date/ })).toBeInTheDocument()
    dispatchKey(new KeyboardEvent("keydown", { key: "g" }))
    expect(await screen.findByLabelText("Date to go to")).toBeInTheDocument()
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

  it("a crossing that names days opens only records with a time and says so (07 XF-1, XF-4)", async () => {
    page("/cases/case-1/conversations?tab=people&people=phone%3A%2B12025550143&from=2023-03-13&to=2023-03-15&notime=0")
    const line = await screen.findByTestId("dated-only")
    expect(line.textContent).toContain("Showing only messages and calls with a time.")
    await waitFor(() => expect(streamFilters.at(-1)).toMatchObject({ include_no_time: false }))
    fireEvent.click(screen.getByRole("button", { name: "Include those with no time" }))
    await waitFor(() => expect(seen.search).not.toContain("notime"))
  })

  it("Write a note about these opens the Notebook with the selection linked, counted and pinned (CO-6)", async () => {
    page()
    await waitFor(() => expect(seen.search).toContain("thread=t1"))
    const write = await screen.findByRole("button", { name: "Write a note about these" })
    expect(write).toBeDisabled()
    const row = (n: number, copies: string[] = []) => ({ event_uid: `ev${n}`, record_uid: `r${n}`, copies: { record_uids: copies }, line: `synthetic ${n}`, thread: { thread_key: "t1" } })
    const onSel = (listProps.last as unknown as { onSelectionChange: (rows: unknown[], all: boolean) => void }).onSelectionChange
    act(() => onSel([row(1, ["r1b"]), row(2)], false))
    fireEvent.click(screen.getByRole("button", { name: "Write a note about these" }))
    const st = useNotebookStore.getState()
    expect(st.draftPhone).toEqual({ caseId: "case-1", selected: 2, linked: 2, recordIds: ["r1", "r2"] })
    expect(st.draftLinks.map((l) => l.target_id)).toEqual(["r1", "r1b", "r2"])
    expect(st.draftLinks.every((l) => l.target_type === "phone_record")).toBe(true)
  })

  it("Ask about these messages waits for a selection, so a conversation is never named when none of it is sent", async () => {
    page()
    await waitFor(() => expect(seen.search).toContain("thread=t1"))
    const ask = await screen.findByRole("button", { name: "Select messages to ask about them" })
    expect(ask).toBeDisabled()
  })
})

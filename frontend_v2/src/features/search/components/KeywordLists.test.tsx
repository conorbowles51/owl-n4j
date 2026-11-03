import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { KeywordList } from "../api"

/** Saved keyword lists (03 section 11.2; 07 J-6 "Saves", section 14) with the server stubbed. Synthetic data only. */
const api = vi.hoisted(() => ({ listKeywordLists: vi.fn(), saveKeywordList: vi.fn(), attachKeywordList: vi.fn() }))
vi.mock("../api", async (orig) => ({ ...(await orig<object>()), ...api }))

import { KeywordListsPage, TheoryKeywordLists } from "./KeywordListsPage"
import { hitsPath } from "../lib/keyword-list-path"
import { SaveKeywordList } from "./SearchDialog"
import { splitTerms } from "../api"
import { TABS, deletionWords } from "@/features/phones/analysis/deletion-words"

const list = (over: Partial<KeywordList> = {}): KeywordList => ({
  entry_id: "kl-1", name: "Vehicles", terms: ["blue van", "dock"], exact: false, created_by: "synthetic",
  created_at: "2026-11-03T22:00:00Z", last_run_at: "2026-11-03T22:01:00Z", state: "current", error: null, theories: [],
  summary: "Last run 2026-11-03 22:01 UTC on 2 phones, 5 matches in all. C4 is still being read, so its counts are incomplete; the list runs again when it finishes.",
  run: {
    phones: [
      { extraction_id: "e1", phone_label: "C3", total: 4, terms: { "blue van": { messages: 2, calls: 0, emails: 0, records: 0, machine_text: 0 }, dock: { messages: 1, calls: 0, emails: 0, records: 1, machine_text: 0 } } },
      { extraction_id: "e2", phone_label: "C4", total: 1, terms: { "blue van": { messages: 0, calls: 0, emails: 0, records: 0, machine_text: 0 }, dock: { messages: 1, calls: 0, emails: 0, records: 0, machine_text: 0 } } },
    ],
    terms: { "blue van": 2, dock: 3 }, total: 5, ran_at: "2026-11-03T22:01:00Z",
    groups: ["messages", "calls", "emails", "records", "machine_text"],
    group_words: { messages: "messages", calls: "calls", emails: "emails", records: "other phone records", machine_text: "text read from photos and audio" },
    not_counted: [{ extraction_id: "e2", phone_label: "C4", state: "interpreting", message: "C4 is still being read, so its counts are incomplete; the list runs again when it finishes." }],
  },
  ...over,
})

function wrap(ui: React.ReactNode, path = "/cases/case-1/keyword-lists") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/cases/:id/keyword-lists" element={ui} />
          <Route path="*" element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe("Keyword lists", () => {
  beforeEach(() => {
    api.listKeywordLists.mockReset()
    api.saveKeywordList.mockReset()
  })

  it("shows each list's run, names a phone still reading, and links every total to that phone's hits", async () => {
    api.listKeywordLists.mockResolvedValue({ total: 1, items: [list()] })
    wrap(<KeywordListsPage />)
    expect(await screen.findByText("Vehicles")).toBeInTheDocument()
    expect(screen.getByTestId("keyword-list-summary")).toHaveTextContent("on 2 phones, 5 matches in all")
    expect(screen.getByRole("alert")).toHaveTextContent("C4 is still being read")
    const link = screen.getByRole("link", { name: "2 messages" })
    expect(link.getAttribute("href")).toBe(hitsPath("case-1", "blue van", "messages", "e1", false))
    expect(link.getAttribute("href")).toBe("/cases/case-1/search?q=blue+van&group=messages&phones=e1")
    expect(screen.getByRole("link", { name: "1 other phone records" })).toBeInTheDocument()
  })

  it("says a list not run yet will run, without inventing totals", async () => {
    api.listKeywordLists.mockResolvedValue({ total: 1, items: [list({ state: "not_run", run: null, last_run_at: null, summary: "Not run yet. It runs on every phone in the case within a minute of being saved." })] })
    wrap(<KeywordListsPage />)
    expect(await screen.findByText(/Not run yet/)).toBeInTheDocument()
    expect(screen.queryByRole("table")).toBeNull()
  })

  it("saves the search as a list with the typed terms", async () => {
    api.saveKeywordList.mockResolvedValue(list({ state: "not_run", run: null }))
    const opened = vi.fn()
    wrap(<SaveKeywordList caseId="case-1" q="blue van" exact={false} onOpenLists={opened} />)
    fireEvent.click(screen.getByText("Save as keyword list"))
    expect(screen.getByLabelText("Keyword list name")).toHaveValue("blue van")
    fireEvent.change(screen.getByLabelText("Keyword list name"), { target: { value: "Vehicles" } })
    fireEvent.change(screen.getByLabelText("Keyword list terms"), { target: { value: "blue van\ndock, " } })
    fireEvent.click(screen.getByText("Save list"))
    await waitFor(() => expect(api.saveKeywordList).toHaveBeenCalledWith("case-1", "Vehicles", ["blue van", "dock"], false))
    expect(await screen.findByRole("status")).toHaveTextContent("runs on every phone in the case")
    expect(splitTerms(" a ,\n\nb ")).toEqual(["a", "b"])
  })

  it("shows a theory's lists with their current totals", async () => {
    api.listKeywordLists.mockResolvedValue({ total: 1, items: [list({ theories: [{ id: "th-1", title: "Van theory" }] })] })
    wrap(<TheoryKeywordLists caseId="case-1" theoryId="th-1" />, "/cases/case-1/workspace")
    expect(await screen.findByTestId("theory-keyword-lists")).toHaveTextContent("5 matches in all")
    expect(api.listKeywordLists).toHaveBeenCalledWith("case-1", "th-1")
  })

  it("names a gap the other phone fills (19.S6-c)", () => {
    expect(TABS.map((t) => t.kind)).toContain("hole_confirmed_by_counterpart")
    const w = deletionWords({
      kind: "hole_confirmed_by_counterpart",
      measures: { phone_label: "C1", app: "WhatsApp", gap_days: 27, gap_start: null, gap_end: null, counterpart_phones: ["C2"], counterpart_messages_in_gap: 2, counterpart_absent_here: 1, counterpart_deleted_here: 1 },
    } as never)
    expect(w.title).toContain("while C2 holds messages of it")
    expect(w.line).toContain("1 not on C1, 1 deleted on C1")
  })
})

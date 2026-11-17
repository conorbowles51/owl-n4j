import { beforeEach, describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { corroborateAPI, type Preview } from "./api"
import { DraftOpener } from "./DraftOpener"
import { getSelection } from "./selection-store"

const preview: Preview = {
  members: 2, selected: 2,
  scope: { active: false, words: [], outside: {}, outside_total: 0, no_time: 0, anchors: null, anchors_date_only: 0, kept: null },
  left_out: { count: 0, examples: [] },
  taken: { people: [], times: { from: null, to: null, dated: 0, days: 0, undated: 2 }, places: [], items: [] },
  questions: [
    { kind: "in_contact", text: "Were they in contact?", count: 1, count_words: "1", chips: { when: "w", nights: "n", who: "w", what: "w", compare_with: "c" } },
    { kind: "together", text: "Were they together?", count: 1, count_words: "1", chips: { when: "w", nights: "n", who: "w", what: "w", compare_with: "c" } },
  ],
}
beforeEach(() => { localStorage.clear(); vi.restoreAllMocks() })

describe("The assistant's drafted question", () => {
  it("opens in the composer with the drafted question chosen, says nothing has run, and never runs it", async () => {
    vi.spyOn(corroborateAPI, "draft").mockResolvedValue({ id: "d1", members: [{ type: "phone_record", id: "a" }, { type: "phone_record", id: "b" }], question: { kind: "together", text: "Were they together?" }, drafted_by: "assistant" })
    vi.spyOn(corroborateAPI, "preview").mockResolvedValue(preview)
    const run = vi.spyOn(corroborateAPI, "run")
    render(<QueryClientProvider client={new QueryClient()}><MemoryRouter initialEntries={["/cases/c1/agent?corro_draft=d1"]}>
      <Routes><Route path="/cases/:id/agent" element={<DraftOpener />} /></Routes>
    </MemoryRouter></QueryClientProvider>)
    await screen.findByText(/The assistant drafted this question/)
    await screen.findByText("Your question: Were they together?")
    expect(getSelection("c1")[0].screen).toBe("the assistant")
    expect(run).not.toHaveBeenCalled()
  })
})

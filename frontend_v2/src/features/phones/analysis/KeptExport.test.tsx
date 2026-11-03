import { fireEvent, render, screen, within } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { describe, expect, it, vi } from "vitest"

/** 07 J-14b: a kept result on the analyses page opens in its analysis and exports its records. Invented data only. */
const keptResults = vi.hoisted(() => vi.fn())
const prepareSourceExport = vi.hoisted(() => vi.fn())
vi.mock("./analysis-api", () => ({ analysisAPI: () => ({}), keptResults }))
vi.mock("@/features/phones/api", () => ({ prepareSourceExport, failureText: (_e: unknown, d: string) => d }))
vi.mock("@/features/conversations/ExportDialog", () => ({
  ExportDialog: (p: { open: boolean; words: string; note: string | null; source: string }) =>
    p.open ? <div role="dialog">{p.source}: {p.words}. {p.note}</div> : null,
}))

import AnalysesPage from "./AnalysesPage"

describe("Kept results on the analyses page (J-14b)", () => {
  it("lists each kept result with the full count, links it to its analysis and exports what it was kept with", async () => {
    keptResults.mockResolvedValue({ total: 51, offset: 0, limit: 50, items: [
      { id: "pa_1", label: "Typed words: typed and present, C1 (Lead for enquiry)", approach: "typed_words", record_count: 1, created_by_name: "Synthetic Reviewer", created_at: null }] })
    prepareSourceExport.mockResolvedValue({ selection_id: "s1", filter: { case_id: "c1", selection: "s1" }, collected: 1, events: 1,
      words: "The records behind the kept result", sentence: "1 record behind it is not a message or call and is not in the export; open them on the screen." })
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={["/cases/c1/phone-analyses"]}><Routes><Route path="/cases/:id/phone-analyses" element={<AnalysesPage />} /></Routes></MemoryRouter>
      </QueryClientProvider>)
    const row = await screen.findByTestId("kept-result")
    expect(screen.getByText("51 kept, the latest 1 shown.")).toBeInTheDocument()
    expect(within(row).getByRole("link")).toHaveAttribute("href", "/cases/c1/phone-analyses/typed-words?kept=pa_1")
    expect(row).toHaveTextContent("1 record behind it, kept by Synthetic Reviewer.")
    fireEvent.click(within(row).getByRole("button", { name: "Export…" }))
    expect(await screen.findByRole("dialog")).toHaveTextContent("analysis_result: The records behind the kept result. 1 record behind it is not a message or call")
    expect(prepareSourceExport).toHaveBeenCalledWith("c1", "analysis_result", { kept_id: "pa_1" })
  })
  it("offers no export for a kept result with no records behind it", async () => {
    keptResults.mockResolvedValue({ total: 1, offset: 0, limit: 50, items: [
      { id: "pa_2", label: "Two extractions of one phone: identity check, C1 and C2 (Lead for enquiry)", approach: "extraction_comparison", record_count: 0, created_by_name: null, created_at: null }] })
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={["/cases/c1/phone-analyses"]}><Routes><Route path="/cases/:id/phone-analyses" element={<AnalysesPage />} /></Routes></MemoryRouter>
      </QueryClientProvider>)
    const row = await screen.findByTestId("kept-result")
    expect(row).toHaveTextContent("0 records behind it.")
    expect(within(row).queryByRole("button", { name: "Export…" })).toBeNull()
  })
})

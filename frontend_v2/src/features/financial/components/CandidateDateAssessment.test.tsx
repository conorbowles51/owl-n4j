import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { CandidateDateAssessment } from "./CandidateDateAssessment"
vi.mock("./TransactionSourceHighlight", () => ({
  TransactionSourceHighlight: () => <p>Original source highlight</p>,
}))
afterEach(() => vi.restoreAllMocks())
const result = {
  case_id: "case-a",
  candidate_id: "row-a",
  mapping_id: "mapping-a",
  review_revision: "a".repeat(64),
  assessment_revision: "b".repeat(64),
  applied: false,
  limitation: "No date is selected or admitted.",
  unclassified_columns: [],
  date_cells: [
    {
      column_index: 0,
      proposed_meaning: "booking_date",
      source: { text: "01/02/2026", locator: { kind: "page_only", page: 1 } },
      assessment: {
        raw: "01/02/2026",
        origin: "digital_text_layer",
        status: "ambiguous_order",
        requires_source_review: true,
        explanation: "Both date orders are valid.",
        glyph_limitation: "Review original glyphs.",
        proposals: [
          { order: "day-month-year", iso_date: "2026-02-01" },
          { order: "month-day-year", iso_date: "2026-01-02" },
        ],
      },
    },
  ],
}
function mount(data: unknown = result) {
  const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify(data), {
      headers: { "Content-Type": "application/json" },
    })
  )
  render(
    <QueryClientProvider client={new QueryClient()}>
      <CandidateDateAssessment
        caseId="case-a"
        candidateId="row-a"
        mappingId="mapping-a"
        fileId="file-a"
        reviewRevision={"a".repeat(64)}
      />
    </QueryClientProvider>
  )
  return fetch
}
it("assesses only on request and displays both date proposals with original source", async () => {
  const fetch = mount()
  expect(fetch).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole("button", { name: "Assess original dates" }))
  expect(await screen.findByText(/2026-02-01/)).toBeInTheDocument()
  expect(screen.getByText(/2026-01-02/)).toBeInTheDocument()
  expect(screen.getByText("Original source highlight")).toBeInTheDocument()
  expect(fetch.mock.calls).toHaveLength(1)
  expect(fetch.mock.calls[0][1]?.method ?? "GET").toBe("GET")
  expect(
    screen.queryByRole("button", { name: /apply|select date/i })
  ).not.toBeInTheDocument()
})
it.each([
  { case_id: "other" },
  { candidate_id: "other" },
  { mapping_id: "other" },
  { review_revision: "c".repeat(64) },
  { applied: true },
])("refuses mismatched or applied assessment %j", async (change) => {
  mount({ ...result, ...change })
  fireEvent.click(screen.getByRole("button", { name: "Assess original dates" }))
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Date assessment unavailable"
  )
  expect(screen.queryByText(/2026-02-01/)).not.toBeInTheDocument()
})
it("shows incomplete month/day without a fabricated year", async () => {
  const cell = result.date_cells[0]
  mount({
    ...result,
    date_cells: [
      {
        ...cell,
        source: { text: "01/02" },
        assessment: {
          ...cell.assessment,
          status: "missing_year",
          raw: "01/02",
          proposals: [{ order: "day-month-year", month: 2, day: 1 }],
        },
      },
    ],
  })
  fireEvent.click(screen.getByRole("button", { name: "Assess original dates" }))
  expect(
    await screen.findByText(/month 2, day 1; full year unresolved/)
  ).toBeInTheDocument()
  expect(screen.queryByText(/2026-02-01/)).not.toBeInTheDocument()
})

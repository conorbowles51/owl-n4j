import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, fireEvent } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { CandidatePageScan } from "./CandidatePageScan"
afterEach(() => vi.restoreAllMocks())
const data = {
  case_id: "case",
  evidence_file_id: "file",
  start_page: 1,
  end_page: 2,
  table_index: 0,
  date_column: 0,
  amount_column: 1,
  currency: "GBP",
  applied: false,
  limitation: "No admission",
  suggested_rows: 1,
  pages: [
    {
      page_number: 1,
      checked: true,
      reason: null,
      checked_rows: 4,
      source_revision: "a".repeat(64),
      suggestions: [
        {
          row_index: 2,
          date_source: { column_index: 0, expected_text: "May 29" },
          amount_source: { column_index: 1, expected_text: "123.45" },
        },
      ],
    },
    {
      page_number: 2,
      checked: false,
      reason: "No stored table",
      checked_rows: 0,
      suggestions: [],
    },
  ],
}
function mount(value: unknown = data) {
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValue(new Response(JSON.stringify(value)))
  const onPage = vi.fn()
  render(
    <QueryClientProvider client={new QueryClient()}>
      <CandidatePageScan caseId="case" fileId="file" onPage={onPage} />
    </QueryClientProvider>
  )
  return { fetch, onPage }
}
async function scan() {
  fireEvent.click(
    screen.getByRole("button", { name: "Find possible rows across PDF pages" })
  )
  fireEvent.change(screen.getByLabelText("Scan through page"), {
    target: { value: "2" },
  })
  fireEvent.change(screen.getByLabelText("Scan currency"), {
    target: { value: "GBP" },
  })
  fireEvent.click(
    screen.getByRole("button", { name: "Scan selected page range" })
  )
}
it("shows checked and unchecked pages and opens a page without saving rows", async () => {
  const { fetch, onPage } = mount()
  expect(fetch).not.toHaveBeenCalled()
  await scan()
  await screen.findByText(/1 possible rows across 1 checked pages/)
  expect(screen.getByText(/Row 3: May 29 · 123.45/)).toBeInTheDocument()
  fireEvent.click(screen.getByRole("button", { name: "Inspect PDF page 1" }))
  expect(onPage).toHaveBeenCalledWith(1)
  expect(fetch.mock.calls[0][1]?.method).not.toBe("POST")
})
it("refuses incomplete page results", async () => {
  mount({ ...data, pages: data.pages.slice(0, 1) })
  await scan()
  expect(await screen.findByRole("alert")).toHaveTextContent("incomplete scope")
})

import { fireEvent, render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, expect, it, vi } from "vitest"
import { CandidateRowSuggestions } from "./CandidateRowSuggestions"
afterEach(() => vi.restoreAllMocks())
const source = {
  case_id: "case",
  evidence_file_id: "file",
  page_number: 1,
  table_index: 0,
  source_revision: "a".repeat(64),
  rows: [
    {
      row_index: 2,
      cells: [
        { column_index: 0, expected_text: "7 September 2026" },
        { column_index: 1, expected_text: "1234" },
      ],
    },
  ],
}
const answer = {
  ...source,
  date_column: 0,
  amount_column: 1,
  currency: "GBP",
  currency_source: "caller_supplied",
  checked_rows: 1,
  suggested_rows: 1,
  applied: false,
  requires_source_review: true,
  limitation: "No automatic admission.",
  rows: [
    {
      row_index: 2,
      suggested: true,
      reason: "Inspect source.",
      date_source: source.rows[0].cells[0],
      amount_source: source.rows[0].cells[1],
      date_assessment: {
        status: "unambiguous_format",
        explanation: "Review glyphs.",
      },
      amount_assessment: { explanation: "Uncertain separators." },
      amount_error: null,
    },
  ],
}
function mount(data: unknown = answer) {
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async () => new Response(JSON.stringify(data)))
  const onSelect = vi.fn(),
    client = new QueryClient()
  render(
    <QueryClientProvider client={client}>
      <CandidateRowSuggestions
        source={source}
        columns={{ 0: "transaction_date", 1: "amount" }}
        onSelect={onSelect}
      />
    </QueryClientProvider>
  )
  return { fetch, onSelect }
}
function request() {
  fireEvent.change(screen.getByLabelText("Date column for suggestions"), {
    target: { value: "0" },
  })
  fireEvent.change(screen.getByLabelText("Amount column for suggestions"), {
    target: { value: "1" },
  })
  fireEvent.change(screen.getByLabelText("Currency context for suggestions"), {
    target: { value: "GBP" },
  })
  fireEvent.click(
    screen.getByRole("button", { name: "Inspect row suggestions" })
  )
}
it("requires explicit inputs and explicit selection after source review", async () => {
  const { fetch, onSelect } = mount()
  expect(
    screen.getByRole("button", { name: "Inspect row suggestions" })
  ).toBeDisabled()
  expect(fetch).not.toHaveBeenCalled()
  request()
  await screen.findByText("1 suggested from 1 checked rows.")
  expect(onSelect).not.toHaveBeenCalled()
  expect(screen.getByText(/7 September 2026/)).toBeInTheDocument()
  fireEvent.click(
    screen.getByRole("button", {
      name: "Add suggested rows to review selection",
    })
  )
  expect(onSelect).toHaveBeenCalledWith([2])
  expect(fetch).toHaveBeenCalledTimes(1)
})
it.each([
  { case_id: "other" },
  { source_revision: "b".repeat(64) },
  { date_column: 1 },
  { currency: "USD" },
  { checked_rows: 2 },
  { rows: [] },
  {
    rows: [
      {
        ...answer.rows[0],
        amount_source: { column_index: 1, expected_text: "changed" },
      },
    ],
  },
])("refuses source or scope mismatch %j", async (change) => {
  const { onSelect } = mount({ ...answer, ...change })
  request()
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Suggestions unavailable"
  )
  expect(onSelect).not.toHaveBeenCalled()
  expect(
    screen.queryByRole("button", {
      name: "Add suggested rows to review selection",
    })
  ).not.toBeInTheDocument()
})
it("clears suggestions when currency context changes", async () => {
  mount()
  request()
  await screen.findByText("1 suggested from 1 checked rows.")
  fireEvent.change(screen.getByLabelText("Currency context for suggestions"), {
    target: { value: "USD" },
  })
  expect(
    screen.queryByRole("button", {
      name: "Add suggested rows to review selection",
    })
  ).not.toBeInTheDocument()
})

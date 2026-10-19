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
async function scan(automatic = false) {
  fireEvent.click(
    screen.getByRole("button", { name: "Find possible rows across PDF pages" })
  )
  if (automatic)
    fireEvent.click(screen.getByLabelText("Propose columns on each page"))
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
it("proposes per-page columns without sending fixed positions", async () => {
  const { fetch } = mount({
    ...data,
    auto_columns: true,
    date_column: null,
    amount_column: null,
    pages: [
      {
        ...data.pages[0],
        chosen_columns: {
          date_column: 0,
          amount_column: 1,
          supporting_rows: 2,
          header_support: 0,
        },
      },
      data.pages[1],
    ],
  })
  fireEvent.click(
    screen.getByRole("button", { name: "Find possible rows across PDF pages" })
  )
  fireEvent.click(screen.getByLabelText("Propose columns on each page"))
  expect(screen.getByLabelText("Possible date column")).toBeDisabled()
  fireEvent.change(screen.getByLabelText("Scan through page"), {
    target: { value: "2" },
  })
  fireEvent.change(screen.getByLabelText("Scan currency"), {
    target: { value: "GBP" },
  })
  fireEvent.click(
    screen.getByRole("button", { name: "Scan selected page range" })
  )
  await screen.findByText(/Date column 1, amount column 2/)
  expect(String(fetch.mock.calls[0][0])).toContain("auto_columns=true")
  expect(String(fetch.mock.calls[0][0])).not.toContain("date_column=")
})

it("shows undated charge evidence even when dated column selection is unavailable", async () => {
  const { onPage } = mount({
    ...data,
    suggested_rows: 0,
    undated_charge_rows: 1,
    pages: [
      {
        ...data.pages[0],
        checked: false,
        reason: "No dated layout",
        suggestions: [],
        undated_checked_rows: 4,
        undated_charges: [
          {
            row_index: 3,
            label_source: {
              column_index: 0,
              expected_text: "Interest Charge on Purchases",
            },
            amount_sources: [{ column_index: 1, expected_text: "$56.16" }],
            date_unknown: true,
            reason: "No date is inferred.",
          },
        ],
      },
      data.pages[1],
    ],
  })
  await scan()
  expect(
    await screen.findByText(/Undated row 4: Interest Charge on Purchases/)
  ).toBeInTheDocument()
  expect(screen.getByText("Column 2: $56.16")).toBeInTheDocument()
  fireEvent.click(screen.getByRole("button", { name: "Inspect PDF page 1" }))
  expect(onPage).toHaveBeenCalledWith(1)
})

it("retains both labelled amount columns for source review", async () => {
  mount({
    ...data,
    pages: [
      {
        ...data.pages[0],
        chosen_columns: {
          date_column: 0,
          amount_column: 1,
          additional_amount_columns: [2],
        },
        suggestions: [
          {
            ...data.pages[0].suggestions[0],
            amount_header_source: {
              column_index: 1,
              expected_text: "Money out",
            },
          },
        ],
      },
      data.pages[1],
    ],
  })
  await scan()
  expect(
    await screen.findByText(/additional amount column 3/)
  ).toBeInTheDocument()
  expect(
    screen.getByText(/source header “Money out” \(review direction\)/)
  ).toBeInTheDocument()
})

const section = {
  start_row: 1,
  end_row: 4,
  start_source: { column_index: 0, expected_text: "Transactions" },
  end_source: { column_index: 0, expected_text: "Totals Year-to-Date" },
  omitted_rows: 10,
  limitation: "Outside rows remain unchecked.",
}
it("shows the printed section boundaries and rows left outside the scan", async () => {
  mount({
    ...data,
    auto_columns: true,
    date_column: null,
    amount_column: null,
    pages: [{ ...data.pages[0], source_section: section }, data.pages[1]],
  })
  await scan(true)
  expect(await screen.findByText(/Printed section:/)).toHaveTextContent(
    "10 other rows remain outside this scan"
  )
})
it("refuses a suggestion outside its declared printed section", async () => {
  mount({
    ...data,
    auto_columns: true,
    date_column: null,
    amount_column: null,
    pages: [
      {
        ...data.pages[0],
        source_section: { ...section, start_row: 2, end_row: 5 },
      },
      data.pages[1],
    ],
  })
  await scan(true)
  expect(await screen.findByRole("alert")).toHaveTextContent("incomplete scope")
})

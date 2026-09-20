import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { PreviousStatementReviews } from "./PreviousStatementReviews"

vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
const recovery = {
  revision: "revision",
  required: true,
  acknowledged: false,
  unmatched_count: 1,
  reviews: [
    {
      id: "old",
      filename: "Original.pdf",
      evidence_file_id: "old-file",
      origin: "Bulk review",
      holder: "Synthetic holder",
      account: "TEST123",
      currency: "EUR",
      period_start: "2023-01-01",
      period_end: "2023-12-31",
      row_count: 31,
      changed_row_count: 1,
      period_found: false,
      saved_at: "2026-09-17T10:00:00Z",
    },
  ],
}
const row = {
  id: "row",
  date: "2023-03-18",
  description: "Corrected payment",
  counterparty: "Synthetic payer",
  direction: "credit",
  amount_minor: "12500",
  balance_minor: "22500",
  excluded: false,
  reason: "Checked the PDF",
}
const detail = {
  case_id: "case",
  evidence_file_id: "new-file",
  review_id: "old",
  row_count: 31,
  offset: 0,
  request: {
    expected_revision: "old-reading",
    holder: "Synthetic holder",
    account_number: "TEST123",
    institution: "Synthetic Bank",
    period_start: "2023-01-01",
    period_end: "2023-12-31",
    _saved_balance_corrections: { opening: { amount_minor: "6000", page: 1 } },
    rows: [row],
  },
}
beforeEach(() => {
  vi.mocked(fetchAPI).mockReset()
})
function mount() {
  const compared = vi.fn()
  render(
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: {
            queries: { retry: false },
            mutations: { retry: false },
          },
        })
      }
    >
      <PreviousStatementReviews
        caseId="case"
        fileId="new-file"
        recovery={recovery}
        canEdit
        onCompared={compared}
      />
    </QueryClientProvider>
  )
  return compared
}
it("opens unmatched bulk corrections in pages and records a file comparison only on explicit action", async () => {
  vi.mocked(fetchAPI).mockImplementation(async (_url, options) =>
    options?.method === "POST"
      ? { case_id: "case", evidence_file_id: "new-file", revision: "revision" }
      : detail
  )
  const compared = mount()
  expect(fetchAPI).not.toHaveBeenCalled()
  fireEvent.click(screen.getByText("Compare earlier values"))
  fireEvent.change(screen.getByLabelText("Earlier review"), {
    target: { value: "old" },
  })
  await screen.findByText("Corrected payment")
  expect(
    screen.getByLabelText("Balances corrected after import")
  ).toHaveTextContent("Opening balance: 60.00 EUR · PDF page 1")
  expect(screen.getByText("125.00 EUR")).toBeInTheDocument()
  expect(screen.getByText("Checked the PDF")).toBeInTheDocument()
  fireEvent.click(screen.getByRole("button", { name: "Next saved rows" }))
  await waitFor(() =>
    expect(fetchAPI).toHaveBeenCalledWith(expect.stringContaining("offset=30"))
  )
  expect(compared).not.toHaveBeenCalled()
  expect(
    screen.getByRole("button", { name: "Save comparison for this file" })
  ).toBeDisabled()
  fireEvent.click(screen.getByRole("checkbox"))
  fireEvent.click(
    screen.getByRole("button", { name: "Save comparison for this file" })
  )
  await waitFor(() => expect(compared).toHaveBeenCalledWith("revision"))
  expect(fetchAPI).toHaveBeenCalledWith(
    expect.stringContaining("previous-reviews/compare"),
    {
      method: "POST",
      body: { expected_revision: "revision" },
    }
  )
})
it("keeps a failed or stale comparison unresolved", async () => {
  vi.mocked(fetchAPI).mockRejectedValue(
    Error("Saved reviews changed. Reload this file.")
  )
  const compared = mount()
  fireEvent.click(screen.getByRole("checkbox"))
  fireEvent.click(
    screen.getByRole("button", { name: "Save comparison for this file" })
  )
  await screen.findByRole("alert")
  expect(compared).not.toHaveBeenCalled()
  expect(
    screen.getByRole("button", { name: "Save comparison for this file" })
  ).toBeEnabled()
})

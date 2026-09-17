import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter, useLocation } from "react-router-dom"
import { beforeEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { FinancialBatchPanel } from "./FinancialBatchPanel"
import { useBatchReview } from "../lib/batch-review-context"
vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({ canEdit: true }),
}))
vi.mock("./StatementImportPanel", () => ({
  StatementImportPanel: () => {
    const ctx = useBatchReview()
    return (
      <>
        <p>Focused row: {ctx?.rowId}</p>
        <p>Saved holder: {ctx?.draft?.holder}</p>
        <button
          onClick={async () => {
            await ctx!.save({ checked: true })
            ctx!.saved()
          }}
        >
          Save for bulk import
        </button>
      </>
    )
  },
}))
const item = {
  id: "item",
  file_id: "file",
  statement_id: "period",
  filename: "Checking.pdf",
  status: "attention",
  currency: "EUR",
  transaction_count: 3,
  source_id: "file",
  problems: [{ message: "Check the payment date.", row_id: "1:0:2", page: 1 }],
}
const batch = {
  id: "batch",
  case_id: "case",
  status: "review",
  files: [
    {
      source_id: "file",
      file_id: "file",
      filename: "Checking.pdf",
      status: "checked",
    },
  ],
  counts: { ready: 2, attention: 1, imported: 0 },
  ready_transactions: 14,
  ready_revision: "a".repeat(64),
  total: 1,
  items: [item],
}
function Location() {
  const location = useLocation()
  return <output aria-label="Location">{location.search}</output>
}
function mount() {
  return render(
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
      <MemoryRouter
        initialEntries={["/cases/case/financial?view=statements&batch=batch"]}
      >
        <FinancialBatchPanel caseId="case" />
        <Location />
      </MemoryRouter>
    </QueryClientProvider>
  )
}
beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (options?.method)
      return {
        saved: true,
        status: "ready",
        review_revision: "c".repeat(64),
      } as never
    if (url.includes("/items/"))
      return {
        ...item,
        review_revision: "b".repeat(64),
        review_request: {
          expected_revision: "a".repeat(64),
          holder: "Checked owner",
          account_number: "123",
          institution: "Bank",
          period_start: "2023-01-01",
          period_end: "2023-01-31",
          details_reason: "Checked",
          rows: [],
        },
      } as never
    return batch as never
  })
})
it("confirms the displayed ready list and filters problems across the batch", async () => {
  mount()
  fireEvent.click(
    await screen.findByRole("button", { name: "Import 2 ready statements" })
  )
  await waitFor(() =>
    expect(fetchAPI).toHaveBeenCalledWith(
      "/api/financial/statement-import/batches/batch/confirm?case_id=case",
      { method: "POST", body: { expected_ready_revision: "a".repeat(64) } }
    )
  )
  fireEvent.click(
    screen.getByRole("checkbox", {
      name: "Show statements needing attention only",
    })
  )
  await waitFor(() =>
    expect(fetchAPI).toHaveBeenCalledWith(
      expect.stringContaining("only_problems=true")
    )
  )
  expect(
    await screen.findByText("14 transactions", { exact: false })
  ).toBeVisible()
})
it("opens the exact problem row, reloads server corrections and returns after saving", async () => {
  mount()
  fireEvent.click(await screen.findByRole("button", { name: "Go to this row" }))
  await screen.findByText("Focused row: 1:0:2")
  expect(screen.getByText("Saved holder: Checked owner")).toBeVisible()
  expect(screen.getByLabelText("Location")).toHaveTextContent(
    "batchRow=1%3A0%3A2"
  )
  fireEvent.click(screen.getByRole("button", { name: "Save for bulk import" }))
  await screen.findByRole("heading", { name: "Prepare statements for import" })
  expect(fetchAPI).toHaveBeenCalledWith(
    "/api/financial/statement-import/batches/batch/items/item?case_id=case",
    {
      method: "PUT",
      body: {
        request: { checked: true },
        expected_review_revision: "b".repeat(64),
      },
    }
  )
  expect(screen.getByLabelText("Location")).not.toHaveTextContent("batchItem")
})
it("refuses a response for a different case", async () => {
  vi.mocked(fetchAPI).mockResolvedValue({
    ...batch,
    case_id: "elsewhere",
  } as never)
  mount()
  expect(await screen.findByRole("alert")).toHaveTextContent("another case")
  expect(
    screen.queryByRole("button", { name: "Import 2 ready statements" })
  ).not.toBeInTheDocument()
})

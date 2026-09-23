import { beforeEach, expect, it, vi } from "vitest"
import { render, screen, fireEvent, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"
import { useFinancialDraftStore } from "../stores/financial-drafts"
import { AddSavedStatementPayment } from "./AddSavedStatementPayment"
vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
vi.mock("./TransactionSourceHighlight", () => ({
  TransactionSourceHighlight: () => <p>Original PDF</p>,
}))
const details = {
  case_id: "case",
  source_document_id: "source",
  evidence_file_id: "file",
  revision: "a".repeat(64),
  currency: "MXN",
  pages: [1, 2],
  details: {
    holder: "Example Company",
    institution: "Example Bank",
    account_number: "0001",
  },
}
beforeEach(() => {
  useFinancialDraftStore.setState({ drafts: {} })
  vi.mocked(fetchAPI).mockReset()
})
it("keeps unfinished input, saves to an imported statement and retries a lost response with one identity", async () => {
  let fail = true
  const requests: unknown[] = []
  vi.mocked(fetchAPI).mockImplementation(async (_url, options) => {
    if (options?.method === "POST") {
      requests.push(options.body)
      if (fail) throw Error("Connection interrupted")
      return { transaction_id: "saved-payment" } as never
    }
    return details as never
  })
  const done = vi.fn()
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <AddSavedStatementPayment
        caseId="case"
        sourceId="source"
        onSaved={done}
      />
    </QueryClientProvider>
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Add a missed transaction" })
  )
  await screen.findByText("Original PDF")
  fireEvent.change(screen.getByLabelText("Amount (MXN)"), {
    target: { value: "12.34" },
  })
  fireEvent.change(screen.getByLabelText("Money in or out"), {
    target: { value: "debit" },
  })
  fireEvent.change(screen.getByLabelText("Paid to"), {
    target: { value: "Example supplier" },
  })
  fireEvent.click(screen.getByRole("button", { name: "Close and keep draft" }))
  fireEvent.click(
    screen.getByRole("button", { name: "Add a missed transaction" })
  )
  expect(await screen.findByLabelText("Amount (MXN)")).toHaveValue("12.34")
  fireEvent.change(screen.getByLabelText("Missed payment date"), {
    target: { value: "2026-01-02" },
  })
  fireEvent.change(screen.getByLabelText("Description"), {
    target: { value: "Water payment" },
  })
  fireEvent.click(
    screen.getByRole("button", { name: "Save and open transaction" })
  )
  await screen.findByRole("alert")
  expect(screen.getByLabelText("Paid to")).toHaveValue("Example supplier")
  fail = false
  fireEvent.click(
    screen.getByRole("button", { name: "Save and open transaction" })
  )
  await waitFor(() => expect(done).toHaveBeenCalledWith("saved-payment"))
  expect(requests[1]).toEqual(requests[0])
  expect(requests[0]).toMatchObject({
    row: { direction: "debit", amount_minor: "1234", manual_page: 1 },
  })
})

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, expect, it, vi } from "vitest"
import { LinkedPayments } from "./LinkedPayments"
import { paymentFixture } from "../lib/payment-fixture.test-support"
const api = vi.hoisted(() => vi.fn())
vi.mock("@/lib/api-client", () => ({ fetchAPI: api }))
vi.mock("./SavePaymentSelection", () => ({
  SavePaymentSelection: ({ ids }: { ids: string[] }) => (
    <p>Save: {ids.join(",")}</p>
  ),
}))
const source = {
  case_id: "case",
  transaction_id: "payment",
  ref_id: "TX-123",
  transaction: paymentFixture,
  source_document_id: "document",
  evidence_file_id: "11111111-1111-4111-8111-111111111111",
  filename: "source.pdf",
  sha256_at_ingestion: "a".repeat(64),
  recorded_digest_matches: true,
  file_bytes_verified: false,
  locator_state: "stored",
  locator: { kind: "page_only", page: 1 },
  ledger_status: "admitted",
  superseded_by_id: null,
  limitation: "Stored citation",
}
beforeEach(() => api.mockReset().mockResolvedValue(source))
function mount() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <LinkedPayments caseId="case" ids={["payment"]} />
    </QueryClientProvider>
  )
}
it("loads recognizable payments only when opened and saves the selected identifiers", async () => {
  mount()
  expect(api).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole("button", { name: "View payments (1)" }))
  await screen.findByRole("table", { name: "Investigation transactions" })
  expect(
    screen.getByRole("button", { name: paymentFixture.description! })
  ).toBeInTheDocument()
  fireEvent.click(screen.getByRole("checkbox"))
  expect(screen.getByText("Save: payment")).toBeInTheDocument()
})
it.each([
  { case_id: "foreign" },
  { transaction: { ...paymentFixture, key: "another" } },
  { source_document_id: "another-document" },
])("refuses mismatched payment details %j", async (change) => {
  api.mockResolvedValue({ ...source, ...change })
  mount()
  fireEvent.click(screen.getByRole("button", { name: "View payments (1)" }))
  await screen.findByRole("alert")
  expect(screen.queryByRole("table")).not.toBeInTheDocument()
})

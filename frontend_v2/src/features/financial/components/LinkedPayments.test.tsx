// This existing workflow fixture has case editing and upload access.
vi.mock("../hooks/use-financial-access", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../hooks/use-financial-access")>()),
  useFinancialAccess: () => ({
    canEdit: true,
    canUpload: true,
    ready: true,
    error: false,
  }),
}))
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, expect, it, vi } from "vitest"
import { LinkedPayments } from "./LinkedPayments"
import { paymentFixture } from "../lib/payment-fixture.test-support"
import { useFinancialDraftStore } from "../stores/financial-drafts"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
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
beforeEach(() => {
  api.mockReset().mockResolvedValue({ case_id: "case", sources: [source] })
  useFinancialDraftStore.setState({ drafts: {} })
  useAuthStore.setState({ user: null })
})
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
  api.mockResolvedValue({
    case_id: "case",
    sources: [{ ...source, ...change }],
  })
  mount()
  fireEvent.click(screen.getByRole("button", { name: "View payments (1)" }))
  await screen.findByRole("alert")
  expect(screen.queryByRole("table")).not.toBeInTheDocument()
})

it("keeps analysis selections when the list closes and exposes the same selection to Transactions", async () => {
  mount()
  fireEvent.click(screen.getByRole("button", { name: "View payments (1)" }))
  await screen.findByRole("table")
  fireEvent.click(screen.getByRole("checkbox"))
  expect(
    useFinancialDraftStore.getState().drafts["anonymous:case:selected-payments"]
  ).toEqual(["payment"])
  fireEvent.click(screen.getByRole("button", { name: "Hide payments (1)" }))
  fireEvent.click(screen.getByRole("button", { name: "View payments (1)" }))
  expect(await screen.findByRole("checkbox")).toBeChecked()
  expect(screen.getByText("Save: payment")).toBeInTheDocument()
})
it("includes payments selected in other results and isolates another case and user", async () => {
  useFinancialDraftStore
    .getState()
    .put("anonymous:case:selected-payments", ["elsewhere"])
  const client = new QueryClient()
  const showing = (caseId = "case") => (
    <QueryClientProvider client={client}>
      <LinkedPayments key={caseId} caseId={caseId} ids={["payment"]} />
    </QueryClientProvider>
  )
  const view = render(showing())
  fireEvent.click(screen.getByRole("button", { name: "View payments (1)" }))
  await screen.findByRole("table")
  fireEvent.click(screen.getByRole("checkbox"))
  expect(screen.getByText("Save: elsewhere,payment")).toBeInTheDocument()
  expect(screen.getByText(/1 are outside this result/)).toBeInTheDocument()
  view.rerender(showing("other-case"))
  fireEvent.click(screen.getByRole("button", { name: "View payments (1)" }))
  await screen.findByRole("alert")
  expect(screen.queryByText(/Save:/)).not.toBeInTheDocument()
  view.rerender(showing())
  fireEvent.click(screen.getByRole("button", { name: "View payments (1)" }))
  expect(await screen.findByRole("checkbox")).toBeChecked()
  act(() =>
    useAuthStore.setState({
      user: { id: "another-user", username: "another-user" } as NonNullable<
        ReturnType<typeof useAuthStore.getState>["user"]
      >,
    })
  )
  expect(screen.getByRole("checkbox")).not.toBeChecked()
  expect(screen.queryByText(/Save:/)).not.toBeInTheDocument()
})

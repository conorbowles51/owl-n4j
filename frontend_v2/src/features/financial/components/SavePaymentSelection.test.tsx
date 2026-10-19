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
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, expect, it, vi } from "vitest"
import { SavePaymentSelection } from "./SavePaymentSelection"
import { paymentFixture } from "../lib/payment-fixture.test-support"
import { useFinancialDraftStore } from "../stores/financial-drafts"
const mocks = vi.hoisted(() => ({ fetch: vi.fn(), save: vi.fn() }))
vi.mock("@/lib/api-client", () => ({ fetchAPI: mocks.fetch }))
vi.mock("@/features/workspace/hooks/use-casework", () => ({
  useCreateCaseworkEntry: () => ({ mutateAsync: mocks.save }),
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
  mocks.fetch
    .mockReset()
    .mockResolvedValue({ case_id: "case", sources: [source] })
  mocks.save.mockReset().mockResolvedValue({ id: "saved", case_id: "case" })
  useFinancialDraftStore.setState({ drafts: {} })
})
function mount(ids = ["payment"]) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <SavePaymentSelection caseId="case" ids={ids} />
    </QueryClientProvider>
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Save selection with a note" })
  )
  fireEvent.change(screen.getByLabelText("Name for this selection"), {
    target: { value: "Investigate payment" },
  })
  fireEvent.change(screen.getByLabelText("What did you notice?"), {
    target: { value: "Ask about the recipient" },
  })
  fireEvent.click(
    screen.getByRole("button", { name: "Save payments and note" })
  )
}
it("saves the selected source references and frozen exact values after checking the current row", async () => {
  mount()
  await screen.findByText(/Selection saved/)
  expect(mocks.save).toHaveBeenCalledWith(
    expect.objectContaining({
      title: "Investigate payment",
      links: [
        expect.objectContaining({
          target_id: source.evidence_file_id,
          source_anchor: {
            financial_transaction_ids: ["payment"],
            financial_ref_ids: ["TX-123"],
          },
          metadata: {
            schema: "loupe.financial.payment_selection/1",
            transactions: [
              expect.objectContaining({ amount_minor: "9007199254740993" }),
            ],
          },
        }),
      ],
    })
  )
  expect(Object.keys(useFinancialDraftStore.getState().drafts)).toHaveLength(0)
})
it.each([
  { case_id: "another-case" },
  { ledger_status: "superseded", superseded_by_id: "replacement" },
])("refuses changed or foreign records before saving %j", async (change) => {
  mocks.fetch.mockResolvedValue({
    case_id: "case",
    sources: [{ ...source, ...change }],
  })
  mount()
  await screen.findByRole("alert")
  expect(mocks.save).not.toHaveBeenCalled()
  expect(screen.getByLabelText("What did you notice?")).toHaveValue(
    "Ask about the recipient"
  )
})
it("retains the note and prevents automatic retry after an uncertain save", async () => {
  mocks.save.mockRejectedValue(Error("Connection lost"))
  mount()
  await screen.findByRole("alert")
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Save payments and note" })
    ).toBeDisabled()
  )
  expect(mocks.save).toHaveBeenCalledTimes(1)
  expect(screen.getByLabelText("What did you notice?")).toHaveValue(
    "Ask about the recipient"
  )
})

it("names a changed payment and opens selection review without losing the note", async () => {
  const review = vi.fn()
  mocks.fetch.mockResolvedValue({
    case_id: "case",
    sources: [
      {
        ...source,
        ledger_status: "superseded",
        superseded_by_id: "replacement",
        transaction: {
          ...paymentFixture,
          description: "Example Supplies",
          ledger_status: "superseded",
          superseded_by_id: "replacement",
        },
      },
    ],
  })
  render(
    <QueryClientProvider client={new QueryClient()}>
      <SavePaymentSelection
        caseId="case"
        ids={["payment"]}
        onReviewSelection={review}
      />
    </QueryClientProvider>
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Save selection with a note" })
  )
  fireEvent.change(screen.getByLabelText("Name for this selection"), {
    target: { value: "Keep selected work" },
  })
  fireEvent.change(screen.getByLabelText("What did you notice?"), {
    target: { value: "Check original and correction" },
  })
  fireEvent.click(
    screen.getByRole("button", { name: "Save payments and note" })
  )
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Example Supplies (2026-09-01)"
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Review selected payments" })
  )
  expect(review).toHaveBeenCalledOnce()
  expect(mocks.save).not.toHaveBeenCalled()
  expect(
    Object.values(useFinancialDraftStore.getState().drafts)
  ).toContainEqual({
    title: "Keep selected work",
    body: "Check original and correction",
  })
})

it("saves all 2700 payments in six bounded batches with their exact values and order", async () => {
  const ids = Array.from({ length: 2700 }, (_, i) => `payment-${i}`)
  mocks.fetch.mockImplementation(async (_url, options) => ({
    case_id: "case",
    sources: options.body.transaction_ids.map((id: string) => ({
      ...source,
      transaction_id: id,
      ref_id: id,
      transaction: { ...paymentFixture, key: id, ref_id: id },
    })),
  }))
  mount(ids)
  await screen.findByText(/Selection saved/)
  expect(mocks.fetch).toHaveBeenCalledTimes(6)
  const link = mocks.save.mock.calls[0][0].links[0]
  expect(link.source_anchor.financial_transaction_ids).toEqual(ids)
  expect(link.metadata.transactions).toHaveLength(2700)
  expect(link.metadata.transactions.at(-1).amount_minor).toBe(
    paymentFixture.amount_minor
  )
})
it("refuses a missing final batch without saving a partial selection", async () => {
  const ids = Array.from({ length: 501 }, (_, i) => `payment-${i}`)
  mocks.fetch.mockImplementation(async (_url, options) => ({
    case_id: "case",
    sources:
      options.body.transaction_ids.length === 1
        ? []
        : options.body.transaction_ids.map((id: string) => ({
            ...source,
            transaction_id: id,
            transaction: { ...paymentFixture, key: id },
          })),
  }))
  mount(ids)
  await screen.findByRole("alert")
  expect(mocks.save).not.toHaveBeenCalled()
})

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
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, expect, it, vi } from "vitest"
import {
  PaymentDocumentReview,
  SavedPaymentDocument,
} from "./PaymentDocumentReview"
import {
  wireFixture,
  wireCapture,
  receiptFixture,
} from "../lib/payment-document.test-support"
import { paymentFixture } from "../lib/payment-fixture.test-support"
import { useFinancialDraftStore } from "../stores/financial-drafts"
import { fetchAPI } from "@/lib/api-client"
vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
vi.mock("./TransactionSourceHighlight", () => ({
  TransactionSourceHighlight: ({
    sourceDocumentId,
  }: {
    sourceDocumentId: string
  }) => <div>Original PDF {sourceDocumentId}</div>,
}))
vi.mock("./LedgerSourceDialog", () => ({
  LedgerSourceDialog: ({ transactionId }: { transactionId: string }) => (
    <div>Payment source {transactionId}</div>
  ),
}))
const api = vi.mocked(fetchAPI)
beforeEach(() => {
  api.mockReset()
  useFinancialDraftStore.setState({ drafts: {} })
})
function mount(data = wireFixture) {
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
      <PaymentDocumentReview data={data} />
    </QueryClientProvider>
  )
}
it("keeps original values, requires a correction reason and saves the review without creating a payment", async () => {
  api.mockResolvedValue({
    case_id: "case",
    entry_id: "saved",
    created: true,
    transaction_count: 0,
  })
  const view = mount()
  fireEvent.change(screen.getByLabelText("Sending party", { exact: true }), {
    target: { value: "CORRECTED SENDER" },
  })
  expect(screen.getByText("EXAMPLE SENDER", { exact: false })).toBeVisible()
  const button = screen.getByRole("button", {
    name: "Save wire review",
  })
  expect(button).toBeDisabled()
  fireEvent.change(
    screen.getByLabelText("Correction or check for sending party"),
    { target: { value: "Read the name on the original." } }
  )
  fireEvent.click(button)
  await screen.findByText(/Wire review saved in Findings/)
  expect(api).toHaveBeenCalledWith(
    expect.stringContaining("/payment-document/save?case_id=case"),
    expect.objectContaining({
      body: expect.objectContaining({
        values: expect.objectContaining({ sending_party: "CORRECTED SENDER" }),
        reasons: { sending_party: "Read the name on the original." },
        transaction_id: null,
        expected_revision: wireFixture.revision,
      }),
    })
  )
  expect(screen.getByRole("link", { name: "Open Findings" })).toHaveAttribute(
    "href",
    "/cases/case/financial?view=findings"
  )
  expect(button).toBeDisabled()
  view.unmount()
  mount()
  expect(
    screen.getByRole("button", { name: "Save wire review" })
  ).toBeDisabled()
  fireEvent.click(screen.getByRole("button", { name: "Create another review" }))
  expect(screen.getByRole("button", { name: "Save wire review" })).toBeEnabled()
  expect(screen.getByLabelText("Sending party", { exact: true })).toHaveValue(
    "CORRECTED SENDER"
  )
})
it("requires an explicit link and explanation, and retains the selected source after reopening the draft", async () => {
  api.mockResolvedValue({
    case_id: "case",
    more_matches: false,
    explanation: "Check both sources",
    candidates: [
      {
        transaction_id: "payment",
        transaction: {
          ...paymentFixture,
          amount_minor: "12000",
          currency: "USD",
        },
        filename: "statement.pdf",
        revision: "c".repeat(64),
      },
    ],
  })
  const view = mount()
  fireEvent.click(
    screen.getByRole("button", { name: "Find matching payments" })
  )
  fireEvent.click(await screen.findByRole("radio"))
  expect(
    screen.getByRole("button", { name: "Save wire review" })
  ).toBeDisabled()
  fireEvent.change(
    screen.getByLabelText(
      "Why does this document support the selected payment?"
    ),
    { target: { value: "Same reference and amount." } }
  )
  view.unmount()
  mount()
  expect(
    screen.getByLabelText(
      "Why does this document support the selected payment?"
    )
  ).toHaveValue("Same reference and amount.")
  fireEvent.click(
    screen.getByRole("button", { name: "Open selected payment and source" })
  )
  expect(screen.getByText("Payment source payment")).toBeVisible()
  api.mockResolvedValue({
    case_id: "case",
    entry_id: "saved",
    created: true,
    transaction_count: 0,
  })
  fireEvent.click(screen.getByRole("button", { name: "Save wire review" }))
  await screen.findByText(/Wire review saved in Findings/)
  expect(api.mock.calls.at(-1)?.[1]?.body).toEqual(
    expect.objectContaining({
      transaction_id: "payment",
      transaction_revision: "c".repeat(64),
      link_reason: "Same reference and amount.",
    })
  )
})
it("keeps entered work after a failed save and reuses the request identifier on retry", async () => {
  api.mockRejectedValueOnce(new Error("Connection interrupted"))
  mount()
  fireEvent.change(screen.getByLabelText("Your observations"), {
    target: { value: "Keep this note." },
  })
  fireEvent.click(screen.getByRole("button", { name: "Save wire review" }))
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Your review is still here"
  )
  const first = api.mock.calls[0][1]?.body
  api.mockResolvedValue({
    case_id: "case",
    entry_id: "saved",
    created: false,
    transaction_count: 0,
  })
  fireEvent.click(screen.getByRole("button", { name: "Save wire review" }))
  await waitFor(() => expect(api).toHaveBeenCalledTimes(2))
  expect(api.mock.calls[1][1]?.body).toEqual(first)
  await screen.findByText(/Wire review saved in Findings/)
})
it("reopens saved originals and rejects a review attached to the wrong case", () => {
  const captured = wireCapture()
  captured.reviewed_values.sending_party = "CORRECTED SENDER"
  captured.correction_reasons.sending_party = "Checked the PDF."
  const view = render(
    <SavedPaymentDocument
      metadata={captured}
      caseId="case"
      fileId="wire-file"
    />
  )
  fireEvent.click(
    screen.getByText("Compare the saved values with their original readings")
  )
  expect(screen.getByText("Saved: CORRECTED SENDER")).toBeVisible()
  expect(screen.getByText("Original reading: EXAMPLE SENDER")).toBeVisible()
  fireEvent.click(
    screen.getByRole("button", { name: "Open original wire report" })
  )
  expect(screen.getByText("Original PDF wire-file")).toBeVisible()
  view.rerender(
    <SavedPaymentDocument
      metadata={captured}
      caseId="other"
      fileId="wire-file"
    />
  )
  expect(screen.getByRole("alert")).toHaveTextContent("do not match")
  expect(screen.queryByText("Original PDF wire-file")).toBeNull()
})

it("saves a selected receipt and reopens its original page without creating a wire or statement import", async () => {
  api.mockResolvedValue({
    case_id: "case",
    entry_id: "receipt-note",
    created: true,
    transaction_count: 0,
  })
  mount(receiptFixture)
  expect(
    screen.getByRole("region", { name: "Deposit receipt review" })
  ).toBeVisible()
  fireEvent.click(screen.getByRole("button", { name: "Save receipt review" }))
  await screen.findByText(/Receipt review saved in Findings/)
  expect(api).toHaveBeenCalledWith(
    expect.stringContaining("/payment-document/save"),
    expect.objectContaining({
      body: expect.objectContaining({
        document_id: receiptFixture.document_id,
        values: expect.objectContaining({
          payment_amount: "120.00",
          effective_date: "2021-03-23",
        }),
      }),
    })
  )
})
it("uses the selected receipt and effective date for payment suggestions", async () => {
  api.mockResolvedValue({
    case_id: "case",
    candidates: [],
    more_matches: false,
    explanation: "Checked matches",
  })
  mount(receiptFixture)
  fireEvent.click(
    screen.getByRole("button", { name: "Find matching payments" })
  )
  await screen.findByText(/No imported payments match/)
  expect(api).toHaveBeenCalledWith(
    expect.stringContaining("document_id=" + receiptFixture.document_id),
    expect.objectContaining({
      body: { amount: "120.00", currency: "USD", value_date: "2021-03-23" },
    })
  )
})

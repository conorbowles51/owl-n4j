import { useFinancialDraftStore } from "../stores/financial-drafts"
import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, expect, it, vi } from "vitest"
import { TransactionNote } from "./TransactionNote"
import { paymentFixture } from "../lib/payment-fixture.test-support"
const save = vi.hoisted(() => ({
  mutate: vi.fn(),
  isPending: false,
  isSuccess: false,
  isError: false,
  error: new Error("Connection interrupted"),
  data: { case_id: "case" },
}))
vi.mock("@/features/workspace/hooks/use-casework", () => ({
  useCreateCaseworkEntry: () => save,
}))
beforeEach(() => {
  useFinancialDraftStore.setState({ drafts: {} })
  save.mutate.mockReset()
  save.isPending = false
  save.isSuccess = false
  save.isError = false
})
function mount(transaction?: unknown) {
  render(
    <TransactionNote
      caseId="case"
      transactionId="transaction"
      refId="retained-reference"
      fileId="evidence"
      filename="statement.pdf"
      locator={{ kind: "page_only", page: 3 }}
      initialOpen
      transaction={transaction}
    />
  )
}
it("saves the investigator's words with the exact transaction and evidence reference", () => {
  mount()
  expect(
    screen.getByRole("button", { name: "Save investigation note" })
  ).toBeDisabled()
  fireEvent.change(screen.getByLabelText("Your transaction note"), {
    target: { value: "Ask the account holder about this payment." },
  })
  fireEvent.click(
    screen.getByRole("button", { name: "Save investigation note" })
  )
  expect(save.mutate).toHaveBeenCalledWith(
    expect.objectContaining({
      entry_type: "note",
      body: "Ask the account holder about this payment.",
      links: [
        expect.objectContaining({
          target_type: "evidence",
          target_id: "evidence",
          source_anchor: {
            financial_transaction_ids: ["transaction"],
            financial_ref_ids: ["retained-reference"],
            locator: { kind: "page_only", page: 3 },
          },
        }),
      ],
    }),
    expect.objectContaining({ onSuccess: expect.any(Function) })
  )
})
it("retains the displayed payment values with a new note for later reporting", () => {
  const payment = { ...paymentFixture, key: "transaction" }
  mount(payment)
  fireEvent.change(screen.getByLabelText("Your transaction note"), {
    target: { value: "Check the stated purpose." },
  })
  fireEvent.click(
    screen.getByRole("button", { name: "Save investigation note" })
  )
  expect(save.mutate.mock.calls[0][0].links[0].metadata.transactions).toEqual([
    payment,
  ])
})
it("keeps entered text available after an unsuccessful save", () => {
  save.isError = true
  mount()
  fireEvent.change(screen.getByLabelText("Your transaction note"), {
    target: { value: "Keep this investigation note." },
  })
  expect(screen.getByLabelText("Your transaction note")).toHaveValue(
    "Keep this investigation note."
  )
  expect(screen.getByRole("alert")).toHaveTextContent(
    "Check Workspace before trying again"
  )
})

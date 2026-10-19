import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, expect, it, vi } from "vitest"
import type { Transaction } from "../api"
import { useFinancialDraftStore } from "../stores/financial-drafts"
import { AmountEditDialog } from "./AmountEditDialog"

const transaction: Transaction = {
  key: "payment-a",
  amount: 120,
  currency: "EUR",
  from_entity: { key: null, name: null },
  to_entity: { key: null, name: null },
  financial_record_kind: "transaction",
  financial_view_mode: "transaction",
  is_financial_event: true,
  is_evidence_backed_transaction: true,
}
beforeEach(() => useFinancialDraftStore.setState({ drafts: {} }))
function setup(tx = transaction, save = vi.fn().mockResolvedValue({})) {
  const close = vi.fn()
  const show = (record: Transaction, caseId = "case-a") => (
    <AmountEditDialog
      caseId={caseId}
      open
      onOpenChange={close}
      transaction={record}
      onSave={save}
    />
  )
  return { ...render(show(tx)), show, save, close }
}
function edit() {
  fireEvent.change(screen.getByLabelText("New amount"), {
    target: { value: "125.50" },
  })
  fireEvent.change(screen.getByLabelText("Correction reason"), {
    target: { value: "The printed receipt shows 125.50." },
  })
}
const button = () => screen.getByRole("button", { name: "Save Correction" })

it("opens with the selected amount and currency without inventing a missing original amount", () => {
  setup({ ...transaction, amount_corrected: true, original_amount: null })
  expect(screen.getByLabelText("New amount")).toHaveValue(120)
  expect(screen.getByText("120.00 EUR")).toBeVisible()
  expect(screen.getByText(/Original: Not recorded/)).toBeVisible()
  expect(button()).toBeDisabled()
})

it("keeps edits separate between records, cases and changed source amounts", () => {
  const view = setup()
  edit()
  view.rerender(view.show({ ...transaction, key: "payment-b", amount: 60 }))
  expect(screen.getByLabelText("New amount")).toHaveValue(60)
  expect(screen.getByLabelText("Correction reason")).toHaveValue("")
  view.rerender(view.show(transaction, "other-case"))
  expect(screen.getByLabelText("New amount")).toHaveValue(120)
  view.rerender(view.show(transaction))
  expect(screen.getByLabelText("New amount")).toHaveValue(125.5)
  expect(screen.getByLabelText("Correction reason")).toHaveValue(
    "The printed receipt shows 125.50."
  )
  view.rerender(view.show({ ...transaction, amount: 130 }))
  expect(screen.getByLabelText("New amount")).toHaveValue(130)
  expect(screen.getByLabelText("Correction reason")).toHaveValue("")
})

it("retains a rejected save through closing and reopening", async () => {
  const save = vi.fn().mockRejectedValue(new Error("Case access has changed."))
  const first = setup(transaction, save)
  edit()
  fireEvent.click(button())
  await screen.findByRole("alert")
  expect(screen.getByRole("alert")).toHaveTextContent(
    "Case access has changed."
  )
  expect(first.close).not.toHaveBeenCalled()
  first.unmount()
  setup()
  expect(screen.getByLabelText("New amount")).toHaveValue(125.5)
  expect(screen.getByLabelText("Correction reason")).toHaveValue(
    "The printed receipt shows 125.50."
  )
})

it("submits once while pending and clears the draft only on success", async () => {
  let resolve!: () => void
  const save = vi.fn(
    () =>
      new Promise<void>((done) => {
        resolve = done
      })
  )
  const view = setup(transaction, save)
  edit()
  fireEvent.keyDown(screen.getByLabelText("Correction reason"), {
    key: "Enter",
  })
  fireEvent.keyDown(screen.getByLabelText("Correction reason"), {
    key: "Enter",
  })
  expect(save).toHaveBeenCalledExactlyOnceWith(
    125.5,
    "The printed receipt shows 125.50."
  )
  expect(Object.keys(useFinancialDraftStore.getState().drafts)).toHaveLength(1)
  for (const close of screen.getAllByRole("button", { name: "Close" }))
    fireEvent.click(close)
  expect(view.close).not.toHaveBeenCalled()
  await act(async () => resolve())
  await waitFor(() => expect(view.close).toHaveBeenCalledWith(false))
  expect(Object.keys(useFinancialDraftStore.getState().drafts)).toHaveLength(0)
})

it("does not assume dollars when currency was not recorded", () => {
  setup({ ...transaction, currency: undefined })
  expect(screen.getByText("120.00 (currency not recorded)")).toBeVisible()
  expect(screen.queryByText("$120.00")).not.toBeInTheDocument()
})

it("keeps an unreadable original as text and starts its correction empty", async () => {
  const view = setup({ ...transaction, amount: null, raw_amount: "not stated" })
  expect(screen.getByText("Saved amount text: not stated")).toBeVisible()
  expect(screen.getByText("Amount not recorded")).toBeVisible()
  expect(screen.getByLabelText("New amount")).toHaveValue(null)
  expect(button()).toBeDisabled()
  edit()
  fireEvent.click(button())
  await waitFor(() =>
    expect(view.save).toHaveBeenCalledWith(
      125.5,
      "The printed receipt shows 125.50."
    )
  )
})

import { render, screen, fireEvent } from "@testing-library/react"
import { expect, it, vi } from "vitest"
import { PaymentIdentitySuggestions } from "./PaymentIdentitySuggestions"
const row = {
  transaction_id: "one",
  ref_id: "TX-ONE",
  account_id: "account",
  currency: "GBP",
  counterparty_raw: "ACME",
  description: null,
  amount_minor: "100",
  direction: "debit" as const,
  party: null,
  decision_transaction_id: null,
}
const anchor = {
  ...row,
  transaction_id: "anchor",
  ref_id: "TX-ANCHOR",
  party: { id: "party", name: "ACME reviewed" },
  decision_transaction_id: "anchor",
}
it("source inspection and selection are separate and selection is bounded", () => {
  const onSelect = vi.fn(),
    onSource = vi.fn()
  render(
    <PaymentIdentitySuggestions
      readings={[
        anchor,
        ...Array.from({ length: 101 }, (_, i) => ({
          ...row,
          transaction_id: String(i),
        })),
      ]}
      disabled={false}
      onSelect={onSelect}
      onSource={onSource}
    />
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Find possible identity links" })
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Inspect supporting source TX-ANCHOR" })
  )
  expect(onSource).toHaveBeenCalledWith("anchor")
  expect(onSelect).not.toHaveBeenCalled()
  fireEvent.click(
    screen.getByRole("button", {
      name: "Review 100 possible links to ACME reviewed",
    })
  )
  expect(onSelect.mock.calls[0]).toEqual([
    Array.from({ length: 100 }, (_, i) => String(i)),
    "party",
  ])
  expect(
    screen.getByText(/Remaining readings stay unselected/)
  ).toBeInTheDocument()
})
it("keeps conflicting choices visible and refuses selection during saving", () => {
  const props = {
    readings: [
      anchor,
      {
        ...anchor,
        transaction_id: "second",
        party: { id: "other", name: "Other ACME" },
      },
      row,
    ],
    disabled: false,
    onSelect: vi.fn(),
    onSource: vi.fn(),
  }
  const view = render(<PaymentIdentitySuggestions {...props} />)
  fireEvent.click(
    screen.getByRole("button", { name: "Find possible identity links" })
  )
  expect(
    screen.getByText(/More than one reviewed identity/)
  ).toBeInTheDocument()
  view.rerender(<PaymentIdentitySuggestions {...props} disabled={true} />)
  expect(
    screen.getByRole("button", {
      name: "Review 1 possible links to ACME reviewed",
    })
  ).toBeDisabled()
  expect(props.onSelect).not.toHaveBeenCalled()
})

it("requires opting into weaker name variants and retains explicit selection", () => {
  const onSelect = vi.fn()
  render(
    <PaymentIdentitySuggestions
      readings={[
        { ...anchor, counterparty_raw: "Longname Trading" },
        { ...row, counterparty_raw: "Longnane Trading" },
      ]}
      disabled={false}
      onSelect={onSelect}
      onSource={vi.fn()}
    />
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Find possible identity links" })
  )
  expect(
    screen.queryByRole("button", {
      name: "Review 1 possible links to ACME reviewed",
    })
  ).not.toBeInTheDocument()
  fireEvent.click(
    screen.getByLabelText("Include possible spelling and formatting variants")
  )
  expect(
    screen.getByText(/Why suggested: One character differs/)
  ).toBeInTheDocument()
  expect(onSelect).not.toHaveBeenCalled()
  fireEvent.click(
    screen.getByRole("button", {
      name: "Review 1 possible links to ACME reviewed",
    })
  )
  expect(onSelect).toHaveBeenCalledWith(["one"], "party")
})

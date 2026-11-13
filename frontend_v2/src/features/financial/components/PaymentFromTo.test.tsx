import { render, screen, within } from "@testing-library/react"
import { expect, it, vi } from "vitest"
import { PaymentCardList } from "./PaymentCardList"
import { InvestigationTransactionTable } from "./InvestigationTransactionTable"
import type { LedgerTransaction } from "../api"

const base = {
  key: "p1",
  ref_id: "TX-1",
  description: "C19 INTERESES GANADOS",
  currency: "MXN",
  amount_minor: "12000",
  ordering_date: "2026-09-01",
  account_id: "acc1",
  account_label: "Acme Ltd · BBVA Mexico · 0110280038",
  account_holder: "Acme Ltd",
  txn_number: 1,
} as LedgerTransaction
const out = { ...base, direction: "debit", from_name: "Acme Ltd", to_name: "Landlord SA" } as LedgerTransaction
const inn = { ...base, direction: "credit", from_name: "Payer Co", to_name: "Acme Ltd" } as LedgerTransaction
const noName = { ...base, direction: "debit", from_name: "Acme Ltd", to_name: null, counterparty_raw: null } as unknown as LedgerTransaction

function cards(rows: LedgerTransaction[]) {
  render(
    <PaymentCardList rows={rows} selected={[]} expanded={[]} onExpand={vi.fn()} onToggle={vi.fn()} onParty={vi.fn()} />
  )
}

it("card rows start with From then To, money out: holder pays other side", () => {
  cards([out])
  const item = screen.getAllByRole("listitem")[1]!
  const from = within(item).getByTestId("payment-from")
  const to = within(item).getByTestId("payment-to")
  expect(from.textContent).toMatch(/^From\s*Acme Ltd/)
  expect(to.textContent).toMatch(/^To\s*Landlord SA/)
  // From precedes To, and both precede the printed line
  expect(from.compareDocumentPosition(to) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  const printed = within(item).getByText("C19 INTERESES GANADOS")
  expect(to.compareDocumentPosition(printed) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
})
it("card rows for money in put the other side under From", () => {
  cards([inn])
  expect(screen.getByTestId("payment-from").textContent).toMatch(/^From\s*Payer Co/)
  expect(screen.getByTestId("payment-to").textContent).toMatch(/^To\s*Acme Ltd/)
})
it("a missing side reads Not identified", () => {
  cards([noName])
  expect(screen.getByTestId("payment-to").textContent).toMatch(/^To\s*Not identified/)
})
it("table rows lead with From and To columns", () => {
  render(<InvestigationTransactionTable rows={[inn]} selected={[]} onToggle={vi.fn()} />)
  const heads = screen.getAllByRole("columnheader").map((h) => h.textContent)
  expect(heads.slice(0, 3)).toEqual(["Select", "From", "To"])
  const cells = screen.getAllByRole("row")[1]!.querySelectorAll("td")
  expect(cells[1]!.textContent).toBe("Payer Co")
  expect(cells[2]!.textContent).toBe("Acme Ltd")
})
it("card and table lines show the bank, and the printed line wraps instead of being cut off (FIN-15)", () => {
  const withBank = { ...out, account_institution: "BBVA Mexico", description: "A".repeat(160) } as LedgerTransaction
  cards([withBank])
  expect(screen.getByTestId("payment-bank").textContent).toMatch(/Bank\s*BBVA Mexico/)
  const printed = screen.getByText("A".repeat(160))
  expect(printed.className).not.toMatch(/\btruncate\b/)
  expect(printed.className).toMatch(/break-words/)
  render(<InvestigationTransactionTable rows={[withBank]} selected={[]} onToggle={vi.fn()} />)
  expect(screen.getAllByTestId("payment-bank").length).toBe(2)
})

it("a card corrected before import shows the value read beside the corrected value, on its own full-width line", () => {
  cards([
    {
      ...inn,
      amount_minor: "11900",
      review_correction: { changes: [{ field: "amount", read: "12000", saved: "11900" }], reason: "Page prints 119.00." },
    } as LedgerTransaction,
  ])
  const note = screen.getByRole("note", { name: "Corrected before import" })
  expect(note).toHaveTextContent("Amount: read as 120.00 MXN, corrected to 119.00 MXN")
  // Not squeezed into the description column: the note sits outside the card's column grid.
  expect(note.closest(".grid")).toBeNull()
})

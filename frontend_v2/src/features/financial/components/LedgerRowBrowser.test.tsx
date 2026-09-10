import { render, screen, fireEvent } from "@testing-library/react"
import { expect, it, vi } from "vitest"
import { LedgerRowBrowser } from "./LedgerRowBrowser"
import type { LedgerTransaction } from "../api"
vi.mock("./LedgerTable", () => ({
  LedgerTable: ({
    transactions,
    onSource,
  }: {
    transactions: LedgerTransaction[]
    onSource: (r: LedgerTransaction) => void
  }) => (
    <ul>
      {transactions.map((r) => (
        <li key={r.key}>
          <button onClick={() => onSource?.(r)}>{r.key}</button>
        </li>
      ))}
    </ul>
  ),
}))
function row(
  key: string,
  overrides: Partial<LedgerTransaction> = {}
): LedgerTransaction {
  return {
    key,
    currency: "GBP",
    amount_minor: "9007199254740993",
    description: "Payment",
    direction: "debit",
    proof_class: "p3",
    ordering_date: "2026-01-01",
    ...overrides,
  } as LedgerTransaction
}
it("sorts exact amounts and passes the original selected row to source actions", () => {
  const first = row("larger"),
    second = row("smaller", { amount_minor: "9007199254740992" }),
    source = vi.fn()
  render(<LedgerRowBrowser transactions={[first, second]} onSource={source} />)
  fireEvent.change(screen.getByLabelText("Table order"), {
    target: { value: "amount-asc" },
  })
  expect(screen.getAllByRole("listitem").map((r) => r.textContent)).toEqual([
    "smaller",
    "larger",
  ])
  fireEvent.click(screen.getByRole("button", { name: "smaller" }))
  expect(source).toHaveBeenCalledWith(second)
})
it("refuses amount ordering across currencies and searches recorded references", () => {
  render(
    <LedgerRowBrowser
      transactions={[
        row("one", { bank_reference: "Invoice 123" }),
        row("two", { currency: "USD" }),
      ]}
    />
  )
  expect(
    screen.getByRole("option", { name: "Largest amount first (one currency)" })
  ).toBeDisabled()
  fireEvent.change(screen.getByLabelText("Find in loaded rows"), {
    target: { value: "invoice 123" },
  })
  expect(screen.getByText(/1 of 2 loaded rows/)).toBeInTheDocument()
  expect(screen.queryByRole("button", { name: "two" })).not.toBeInTheDocument()
})
it("pages the complete loaded set and resets its page after filtering", () => {
  render(
    <LedgerRowBrowser
      transactions={Array.from({ length: 51 }, (_, i) => row(String(i)))}
    />
  )
  expect(screen.getAllByRole("listitem")).toHaveLength(50)
  fireEvent.click(screen.getByRole("button", { name: "Next ledger rows" }))
  expect(screen.getAllByRole("listitem")).toHaveLength(1)
  fireEvent.change(screen.getByLabelText("Find in loaded rows"), {
    target: { value: "missing" },
  })
  expect(screen.getByText(/No loaded rows match/)).toBeInTheDocument()
})

it("filters inclusive exact ranges, rejects invalid precision and resets on currency change", () => {
  render(
    <LedgerRowBrowser
      transactions={[
        row("larger"),
        row("smaller", { amount_minor: "9007199254740992" }),
      ]}
    />
  )
  expect(screen.getByLabelText("Table minimum amount")).toBeDisabled()
  fireEvent.change(screen.getByLabelText("Table currency"), {
    target: { value: "GBP" },
  })
  fireEvent.change(screen.getByLabelText("Table minimum amount"), {
    target: { value: "90071992547409.93" },
  })
  fireEvent.change(screen.getByLabelText("Table maximum amount"), {
    target: { value: "90071992547409.93" },
  })
  expect(screen.getByRole("button", { name: "larger" })).toBeInTheDocument()
  expect(
    screen.queryByRole("button", { name: "smaller" })
  ).not.toBeInTheDocument()
  fireEvent.change(screen.getByLabelText("Table maximum amount"), {
    target: { value: "1.001" },
  })
  expect(screen.getByRole("alert")).toHaveTextContent("valid amounts")
  expect(
    screen.queryByRole("button", { name: "larger" })
  ).not.toBeInTheDocument()
  fireEvent.change(screen.getByLabelText("Table currency"), {
    target: { value: "" },
  })
  expect(screen.getByLabelText("Table minimum amount")).toHaveValue("")
  expect(screen.getByRole("button", { name: "smaller" })).toBeInTheDocument()
})

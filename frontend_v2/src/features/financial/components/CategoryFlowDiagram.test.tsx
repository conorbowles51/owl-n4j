import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import type { LedgerTransaction } from "../api"
import { CategoryFlowDiagram } from "./CategoryFlowDiagram"

vi.mock("../hooks/use-payment-category-library", () => ({ useCategoryColors: () => new Map() }))
afterEach(cleanup)
const row = (key: string, direction: string, amount: string, category: string, currency = "MXN") =>
  ({ key, direction, amount_minor: amount, currency, category, account_id: "a1", account_label: "BBVA", ordering_date: "2023-10-31", ordering_date_context: "transaction", from_name: key === "big" ? "INDHECA" : undefined }) as unknown as LedgerTransaction

it("draws money in and out by category, keeps the difference, opens a band's payments and the biggest payment", () => {
  const onOpen = vi.fn()
  const onTrace = vi.fn()
  render(
    <CategoryFlowDiagram
      caseId="c"
      rows={[
        row("big", "credit", "1000000", "Transfers"),
        row("u1", "credit", "200000", "Uncategorized"),
        row("o1", "debit", "300000", "Payroll"),
        row("o2", "debit", "100000", "Transfers"),
        row("usd", "credit", "500", "Deposits", "USD"),
      ]}
      onOpen={onOpen}
      onTrace={onTrace}
    />
  )
  // MXN first (4 payments); in 12,000.00, out 4,000.00, kept 8,000.00
  expect(screen.getByRole("button", { name: "MXN · 4" }).getAttribute("aria-pressed")).toBe("true")
  expect(screen.getByRole("img", { name: /^Kept: 8,000\.00 MXN/ })).toBeTruthy()
  fireEvent.click(screen.getByRole("button", { name: /^No category yet in: \+2,000\.00 MXN · 1 payments\. Open these payments/ }))
  expect(onOpen).toHaveBeenLastCalledWith(["u1"], "No category yet · money in")
  fireEvent.click(screen.getByRole("button", { name: /^Payroll out/ }))
  expect(onOpen).toHaveBeenLastCalledWith(["o1"], "Payroll · money out")
  expect(screen.getByText("INDHECA")).toBeTruthy()
  fireEvent.click(screen.getByRole("button", { name: "Trace where it went next →" }))
  expect(onTrace).toHaveBeenCalled()
  fireEvent.click(screen.getByRole("button", { name: "USD · 1" }))
  expect(screen.getByRole("button", { name: /^Deposits in: \+5\.00 USD/ })).toBeTruthy()
  expect(screen.getByRole("link", { name: /Show as table/ }).getAttribute("href")).toBe("#follow-money-tables")
})

it("counts two account records joined by a saved consolidation as one account", () => {
  // d5b330d1: the Overview showed 66 and 65 accounts side by side; joined records count once everywhere.
  render(
    <CategoryFlowDiagram
      caseId="c"
      rows={[
        { ...row("a", "credit", "1000", "Deposits"), account_id: "copy", canonical_account_id: "kept" },
        { ...row("b", "debit", "500", "Fees"), account_id: "kept", canonical_account_id: "kept" },
      ]}
      onOpen={vi.fn()}
    />
  )
  expect(screen.getByText(/^1 account · MXN/)).toBeTruthy()
})

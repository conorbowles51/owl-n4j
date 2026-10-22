import { act, fireEvent, render, screen } from "@testing-library/react"
import { readFileSync } from "node:fs"
import { beforeEach, expect, it, vi } from "vitest"
import { useFinancialDraftStore, financialDraftKey } from "../stores/financial-drafts"
import { ActiveCategoryNotice } from "./PaymentCategoryFilter"

beforeEach(() => useFinancialDraftStore.setState({ drafts: {} }))

it("categories are no longer chosen at the top of the financial page", () => {
  const page = readFileSync("src/features/financial/components/FinancialPage.tsx", "utf8")
  expect(page).not.toMatch(/<PaymentCategoryFilter/)
  // They stay under Transactions, in its payment table.
  const table = readFileSync("src/features/financial/components/LedgerRowBrowser.tsx", "utf8")
  expect(table).toMatch(/<PaymentCategoryFilter/)
})

it("outside Transactions, says which category narrows the payments and leads back to Transactions", () => {
  const onChange = vi.fn()
  const { container } = render(<ActiveCategoryNotice caseId="case" onChange={onChange} />)
  expect(container).toBeEmptyDOMElement()
  act(() => useFinancialDraftStore.getState().put(financialDraftKey("case", "investigation-category"), "Rent"))
  expect(screen.getByLabelText("Category filter")).toHaveTextContent("Showing category: Rent")
  fireEvent.click(screen.getByRole("button", { name: "Change under Transactions" }))
  expect(onChange).toHaveBeenCalled()
  fireEvent.click(screen.getByRole("button", { name: "Show all categories" }))
  expect(screen.queryByLabelText("Category filter")).toBeNull()
})

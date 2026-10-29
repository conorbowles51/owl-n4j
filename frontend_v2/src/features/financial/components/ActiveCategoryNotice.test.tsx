import { act, fireEvent, render, screen } from "@testing-library/react"
import { readFileSync } from "node:fs"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, expect, it, vi } from "vitest"
import { useFinancialDraftStore, financialDraftKey } from "../stores/financial-drafts"
import { ActiveCategoryNotice, PaymentCategoryFilter } from "./PaymentCategoryFilter"

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

it("names every chosen category, and still reads a single category saved by an older link", () => {
  render(<ActiveCategoryNotice caseId="case" onChange={() => {}} />)
  act(() => useFinancialDraftStore.getState().put(financialDraftKey("case", "investigation-category"), ["Rent", "Payroll"]))
  expect(screen.getByLabelText("Category filter")).toHaveTextContent("Showing categories: Rent, Payroll")
})

it("filters by several categories from chips that show counts, including Uncategorized", () => {
  const rows = [{ category: "Rent" }, { category: "Rent" }, { category: "Payroll" }, {}]
  render(
    <QueryClientProvider client={new QueryClient()}>
      <PaymentCategoryFilter caseId="none" rows={rows} />
    </QueryClientProvider>
  )
  const chip = (name: RegExp) => screen.getByRole("button", { name })
  expect(chip(/^All, 4 payments$/)).toHaveAttribute("aria-pressed", "true")
  expect(chip(/^Rent, 2 payments$/)).toBeInTheDocument()
  fireEvent.click(chip(/^Rent, 2 payments$/))
  fireEvent.click(chip(/^Uncategorized, 1 payments$/))
  const stored = () => useFinancialDraftStore.getState().drafts[financialDraftKey("none", "investigation-category")]
  expect(stored()).toEqual(["Rent", "Uncategorized"])
  expect(chip(/^All, 4 payments$/)).toHaveAttribute("aria-pressed", "false")
  fireEvent.click(chip(/^Rent, 2 payments$/))
  expect(stored()).toEqual(["Uncategorized"])
  fireEvent.click(screen.getByRole("button", { name: /Clear categories/ }))
  expect(stored()).toEqual([])
})

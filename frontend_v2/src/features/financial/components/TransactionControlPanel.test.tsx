import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, fireEvent, render, screen, within } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { LedgerRowBrowser } from "./LedgerRowBrowser"
import type { LedgerTransaction } from "../api"
import { useFinancialDraftStore } from "../stores/financial-drafts"
import { defaultTransactionSections } from "../lib/transaction-sections"

vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(async (url: string) => ({
    case_id: new URL(url, "http://test").searchParams.get("case_id"),
    items: [],
    has_more: false,
    total: 0,
    entries: [],
    categories: [],
  })),
}))

function row(index: number): LedgerTransaction {
  return {
    key: `row-${index}`,
    case_id: "controls-case",
    account_id: index % 2 ? "a" : "b",
    account_label: index % 2 ? "Bank A · 001" : "Bank B · 002",
    currency: index % 5 ? "USD" : "MXN",
    amount_minor: String(100 * (index + 1)),
    description: `Payment ${index}`,
    direction: index % 3 ? "debit" : "credit",
    proof_class: "p3",
    ordering_date: `2026-0${(index % 6) + 1}-01`,
  } as LedgerTransaction
}

const transactions = Array.from({ length: 30 }, (_, index) => row(index))

function page() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <LedgerRowBrowser
        investigation
        transactions={transactions}
        exportContext={{ caseId: "controls-case", params: {} }}
      />
    </QueryClientProvider>
  )
}

const tab = () =>
  screen
    .getAllByRole("button", { name: /filters and page controls/ })
    .find((button) => button.getAttribute("aria-controls") === "transaction-controls" && button.closest("[data-testid=transaction-controls-dock]"))!
const panel = () => document.getElementById("transaction-controls")!
const shownCount = () => screen.getByRole("group", { name: "Active filters" }).querySelector("strong")!.textContent

beforeEach(() => {
  localStorage.clear()
  useFinancialDraftStore.setState({ drafts: {} } as never)
})
afterEach(() => vi.restoreAllMocks())

describe("the Transactions control panel", () => {
  it("opens from its tab, collapses on the tab, the close button and Esc, and gives focus back to the tab", () => {
    page()
    expect(tab()).toHaveAttribute("aria-expanded", "false")
    expect(panel()).toHaveAttribute("inert")

    fireEvent.click(tab())
    expect(tab()).toHaveAttribute("aria-expanded", "true")
    expect(panel()).not.toHaveAttribute("inert")
    expect(panel()).toHaveFocus()

    fireEvent.keyDown(panel(), { key: "Escape" })
    expect(tab()).toHaveAttribute("aria-expanded", "false")
    expect(panel()).toHaveAttribute("inert")
    expect(tab()).toHaveFocus()

    fireEvent.click(tab())
    fireEvent.click(tab())
    expect(tab()).toHaveAttribute("aria-expanded", "false")
    expect(tab()).toHaveFocus()

    fireEvent.click(tab())
    fireEvent.click(within(panel()).getByRole("button", { name: "Collapse filters and page controls" }))
    expect(tab()).toHaveAttribute("aria-expanded", "false")
    expect(tab()).toHaveFocus()
  }, 400_000)

  it("holds every filter: account and date scope, payment filters, page switches and display choices", () => {
    page()
    const inside = within(panel())
    for (const name of ["Show on the page", "Accounts and dates", "Payments", "Display"])
      expect(inside.getByRole("region", { name })).toBeInTheDocument()
    for (const label of ["Currency", "Money in or out", "Sort payments", "Table minimum amount", "Table maximum amount"])
      expect(inside.getByLabelText(label)).toBeInTheDocument()
    for (const name of [/^Money in and out/, /^Monthly volume/, /^Where it went/, /^Totals per account/, /^Charts/, /^From & To/, /^Money flow/])
      expect(inside.getByRole("switch", { name })).toBeInTheDocument()
    expect(inside.getByRole("group", { name: "Show payments as" })).toBeInTheDocument()
    // The bar above the table keeps search and downloads only.
    const bar = screen.getByRole("region", { name: "Transaction tools and filters" })
    expect(within(bar).getByLabelText("Search payments")).toBeInTheDocument()
    expect(within(bar).queryByLabelText("Currency")).toBeNull()
  }, 400_000)

  it("starts with the table and the money in/out totals only, and remembers each switch", () => {
    const first = page()
    expect(screen.getByRole("switch", { name: /^Money in and out/ })).toHaveAttribute("aria-checked", "true")
    for (const name of [/^Monthly volume/, /^Where it went/, /^Totals per account/, /^Charts/, /^From & To/, /^Money flow/])
      expect(screen.getByRole("switch", { name })).toHaveAttribute("aria-checked", "false")
    expect(screen.queryByRole("region", { name: "Where the money went" })).toBeNull()

    fireEvent.click(screen.getByRole("switch", { name: /^Where it went/ }))
    fireEvent.click(screen.getByRole("switch", { name: /^Money in and out/ }))
    expect(screen.getByRole("region", { name: "Where the money went" })).toBeInTheDocument()
    first.unmount()

    page()
    expect(screen.getByRole("switch", { name: /^Where it went/ })).toHaveAttribute("aria-checked", "true")
    expect(screen.getByRole("switch", { name: /^Money in and out/ })).toHaveAttribute("aria-checked", "false")
    expect(screen.getByRole("region", { name: "Where the money went" })).toBeInTheDocument()
  }, 400_000)

  it("works when browser storage is refused, as on a plain-http address", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("denied", "SecurityError")
    })
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("denied", "SecurityError")
    })
    page()
    const months = screen.getByRole("switch", { name: /^Monthly volume/ })
    expect(months).toHaveAttribute("aria-checked", String(defaultTransactionSections.months))
    fireEvent.click(months)
    expect(months).toHaveAttribute("aria-checked", String(!defaultTransactionSections.months))
    fireEvent.click(tab())
    expect(tab()).toHaveAttribute("aria-expanded", "true")
  }, 400_000)

  it("shows every filter in force above the table, each removable, with rows shown out of the total", () => {
    page()
    expect(shownCount()).toContain("30 of 30 imported transactions")
    const inside = within(panel())
    fireEvent.change(inside.getByLabelText("Money in or out"), { target: { value: "debit" } })
    fireEvent.change(inside.getByLabelText("Currency"), { target: { value: "USD" } })
    fireEvent.change(inside.getByLabelText("Table minimum amount"), { target: { value: "5" } })
    fireEvent.change(screen.getByLabelText("Search payments"), { target: { value: "Payment" } })
    const debitsInUsdOver5 = transactions.filter((r) => r.direction === "debit" && r.currency === "USD" && Number(r.amount_minor) >= 500).length
    expect(shownCount()).toContain(`${debitsInUsdOver5} of 30 imported transactions`)
    const chips = screen.getByRole("group", { name: "Active filters" })
    expect(chips).toHaveTextContent("4 filters on")
    expect(tab()).toHaveAccessibleName(/4 filters on/)
    for (const name of ["Outgoing", "USD", "At least 5 USD", "Search: “Payment”"])
      expect(within(chips).getByRole("button", { name: `Remove filter ${name}` })).toBeInTheDocument()

    fireEvent.click(within(chips).getByRole("button", { name: "Remove filter Outgoing" }))
    expect(within(chips).queryByRole("button", { name: "Remove filter Outgoing" })).toBeNull()
    expect(inside.getByLabelText("Money in or out")).toHaveValue("")
    expect(chips).toHaveTextContent("3 filters on")
    // Removing the currency also clears the amount range that depended on it.
    fireEvent.click(within(chips).getByRole("button", { name: "Remove filter USD" }))
    fireEvent.click(within(chips).getByRole("button", { name: "Remove filter Search: “Payment”" }))
    expect(chips).toHaveTextContent("No filters on")
    expect(shownCount()).toContain("30 of 30 imported transactions")
  }, 400_000)

  it("never changes the table's rows when a section is switched on or off", () => {
    page()
    fireEvent.change(within(panel()).getByLabelText("Money in or out"), { target: { value: "credit" } })
    const before = shownCount()
    expect(before).toContain("10 of 30")
    const listed = screen.getByRole("list", { name: "Investigation transactions" }).textContent
    for (const name of [/^Money in and out/, /^Monthly volume/, /^Where it went/, /^Totals per account/, /^Charts/, /^From & To/, /^Money flow/]) {
      const toggle = screen.getByRole("switch", { name })
      act(() => fireEvent.click(toggle))
      expect(shownCount()).toBe(before)
      expect(screen.getByRole("list", { name: "Investigation transactions" }).textContent).toBe(listed)
      act(() => fireEvent.click(toggle))
      expect(shownCount()).toBe(before)
    }
  }, 400_000)

  it("steps back to its tab when the naming panel opens beside the table", () => {
    page()
    fireEvent.click(tab())
    expect(tab()).toHaveAttribute("aria-expanded", "true")
    fireEvent.click(screen.getByRole("button", { name: /one by one/ }))
    expect(tab()).toHaveAttribute("aria-expanded", "false")
    expect(panel()).toHaveAttribute("inert")
  }, 400_000)
})

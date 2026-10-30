import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen } from "@testing-library/react"
import { expect, it, vi } from "vitest"
import { LedgerRowBrowser } from "./LedgerRowBrowser"
import type { LedgerTransaction } from "../api"
import { paymentInventory } from "../lib/payment-inventory"

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
// Counts how often the totals are worked out over every matching payment.
vi.mock("../lib/payment-inventory", async (original) => {
  const real = await original<typeof import("../lib/payment-inventory")>()
  return { ...real, paymentInventory: vi.fn(real.paymentInventory) }
})

function row(index: number): LedgerTransaction {
  return {
    key: `row-${index}`,
    case_id: "sections-case",
    account_id: index % 2 ? "a" : "b",
    account_label: index % 2 ? "Bank A · 001" : "Bank B · 002",
    currency: "USD",
    amount_minor: "100",
    description: `Payment ${index}`,
    direction: index % 3 ? "debit" : "credit",
    proof_class: "p3",
    ordering_date: `2026-0${(index % 6) + 1}-01`,
  } as LedgerTransaction
}

it("shows and hides each section at once: the table stays on its page and the totals are not worked out again", () => {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <LedgerRowBrowser
        investigation
        transactions={Array.from({ length: 30 }, (_, index) => row(index))}
        exportContext={{ caseId: "sections-case", params: {} }}
      />
    </QueryClientProvider>
  )
  fireEvent.change(screen.getByLabelText("Rows per page"), { target: { value: "25" } })
  fireEvent.click(screen.getByRole("button", { name: "Next ledger rows" }))
  expect(screen.getByText("26–30 of 30 matching rows")).toBeVisible()
  // Totals per account are where the pass over every payment happens: switch them on first.
  fireEvent.click(screen.getByRole("switch", { name: /Totals per account/ }))
  const passes = vi.mocked(paymentInventory).mock.calls.length
  expect(passes).toBeGreaterThan(0)
  for (const name of [/^Charts/, /^From & To/, /^Money flow/]) {
    const toggle = screen.getByRole("switch", { name })
    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute("aria-checked", "true")
    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute("aria-checked", "false")
  }
  expect(screen.getByText("26–30 of 30 matching rows")).toBeVisible()
  expect(vi.mocked(paymentInventory).mock.calls.length).toBe(passes)
}, 240_000)

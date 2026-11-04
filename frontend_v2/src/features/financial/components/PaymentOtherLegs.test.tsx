import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { PaymentOtherLegs } from "./PaymentOtherLegs"

afterEach(() => vi.restoreAllMocks())

it("loads when opened and lists every possible other leg with its strength, reasons and reasons against", async () => {
  const body = {
    transaction_id: "t1", named_from: "t2",
    candidates: [
      { transaction_id: "t2", date: "2024-03-01", direction: "credit", description: "SPEI RECIBIDO", holder: "BRAVO DOS", institution: "Santander", identifier: "1234", gap_days: 0, level: "moderate", is_the_named_leg: true,
        reasons: { match: ["same amount and currency, money out of one account and into another", "same day", "no name to compare"], substantiation: ["each is the other's only possible partner"], against: [] } },
      { transaction_id: "t3", date: "2024-03-21", direction: "credit", description: "CASH DEPOSIT", holder: "DELTA", institution: "Santander", identifier: "9999", gap_days: 20, level: "weak", is_the_named_leg: false,
        reasons: { match: ["same amount and currency, money out of one account and into another", "20 days apart", "no name to compare"], substantiation: [], against: ["one line is cash"] } },
    ],
    by_level: { strong: 0, moderate: 1, weak: 1, faint: 0 }, left_out: { beyond_days: 4, search_days: 365 }, rule: "Every payment ... rule.",
  }
  const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(body)))
  render(<QueryClientProvider client={new QueryClient()}><PaymentOtherLegs caseId="c" transactionId="t1" /></QueryClientProvider>)
  expect(fetch).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole("button", { name: "Possible other legs of this payment" }))
  expect(await screen.findByText("2 possible: 0 strong, 1 moderate, 1 weak, 0 faint. 4 more than 365 days away are counted, not listed.")).toBeInTheDocument()
  const named = screen.getByRole("listitem", { name: "Possible other leg 2024-03-01" })
  expect(named).toHaveTextContent("Moderate")
  expect(named).toHaveTextContent("the name shown comes from this payment")
  const weak = screen.getByRole("listitem", { name: "Possible other leg 2024-03-21" })
  expect(weak).toHaveTextContent("Weak")
  expect(weak).toHaveTextContent("How well matched: same amount and currency, money out of one account and into another; 20 days apart; no name to compare")
  expect(weak).toHaveTextContent("Against: one line is cash")
})

it("opens a listed possible other leg", async () => {
  const body = {
    transaction_id: "t1", named_from: null,
    candidates: [
      { transaction_id: "t3", date: "2024-03-21", direction: "credit", description: "SPEI", holder: "DELTA", institution: "Santander", identifier: "9999", gap_days: 20, level: "weak", is_the_named_leg: false,
        reasons: { match: ["20 days apart"], substantiation: [], against: [] } },
    ],
    by_level: { strong: 0, moderate: 0, weak: 1, faint: 0 }, left_out: { beyond_days: 0, search_days: 365 }, rule: "rule",
  }
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(body)))
  const onOpen = vi.fn()
  render(<QueryClientProvider client={new QueryClient()}><PaymentOtherLegs caseId="c" transactionId="t1" onOpen={onOpen} /></QueryClientProvider>)
  fireEvent.click(screen.getByRole("button", { name: "Possible other legs of this payment" }))
  fireEvent.click(await screen.findByRole("button", { name: "Open this payment" }))
  expect(onOpen).toHaveBeenCalledWith("t3")
})

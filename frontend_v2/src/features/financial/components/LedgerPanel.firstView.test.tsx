/**
 * The Transactions page's first view: with no filter on, the panel shows the server's figures and one page of rows
 * (GET /ledger-first-view) without reading every payment (GET /ledger); anything that needs every payment reads
 * them first and then works over all of them.
 */
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, expect, it, vi } from "vitest"

import type { LedgerTransaction } from "../api"
import { useFinancialDraftStore } from "../stores/financial-drafts"
import { LedgerPanel } from "./LedgerPanel"

const fetchAPI = vi.hoisted(() => vi.fn())
const downloadCsv = vi.hoisted(() => vi.fn())
vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()),
  fetchAPI,
}))
vi.mock("../lib/transaction-csv", async (original) => ({
  ...(await original<typeof import("../lib/transaction-csv")>()),
  downloadCsv,
}))
vi.mock("../hooks/use-money-trails", () => ({
  useMoneyTrails: () => ({ data: { trails: [] }, error: null, isPending: false }),
}))
vi.mock("../hooks/use-financial-finding-index", () => ({
  useFinancialFindingIndex: () => ({ data: [], isPending: false, isError: false }),
}))

const CASE = "case-1"
function payment(index: number, overrides: Partial<LedgerTransaction> = {}): LedgerTransaction {
  return {
    key: `txn-${index}`, case_id: CASE, account_id: "acct-1", source_document_id: "doc-1", ingestion_run_id: "run-1",
    statement_period_id: null, ref_id: `ref-${index}`, row_index: index, amount_minor: String(100 + index),
    currency: "USD", direction: "debit", running_balance_minor: null, transaction_date: "2024-03-01",
    posted_date: null, value_date: null, effective_date: null, ordering_date: "2024-03-01",
    ordering_date_source: "transaction", description: `PAYMENT ${index}`, counterparty_raw: null,
    transaction_type: null, bank_reference: null, proof_class: "p2", extraction_layer: 1, ledger_status: "admitted",
    quarantine_reason: null, superseded_by_id: null, to_name: index === 3 ? "Needle Shop" : `Shop ${index}`,
    ...overrides,
  } as LedgerTransaction
}
const ALL = Array.from({ length: 60 }, (_, index) => payment(index))

function answer(url: string) {
  const path = new URL(url, "http://test").pathname
  if (path === "/api/financial/ledger-first-view")
    return {
      case_id: CASE, available: true, total: 60, page: 0, page_size: 50, rows: ALL.slice(0, 50),
      currencies: [{ currency: "USD", count: 60, credit: "0", debit: "7770" }],
      unnamed: 0, unconfirmed: 0, touched: 0,
    }
  if (path === "/api/financial/ledger") return { case_id: CASE, transactions: ALL, total: 60 }
  if (path === "/api/financial/ledger-count") return { case_id: CASE, total: 60 }
  return { case_id: CASE, items: [], has_more: false, total: 0, categories: [], entries: [] }
}
const asked = (path: string) =>
  fetchAPI.mock.calls.filter(([url]) => new URL(String(url), "http://test").pathname === path).length

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <LedgerPanel caseId={CASE} investigation params={{}} />
    </QueryClientProvider>
  )
}

beforeEach(() => {
  localStorage.clear()
  useFinancialDraftStore.setState({ drafts: {} })
  fetchAPI.mockReset()
  downloadCsv.mockReset()
  fetchAPI.mockImplementation(async (url: string) => answer(url))
})

it("shows the server's figures and first page without reading every payment", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  try {
    show()
    expect(await screen.findByText(/60 of 60 imported transactions/)).toBeTruthy()
    expect(screen.getByText("Download CSV (60)")).toBeTruthy()
    expect(screen.getByText("PAYMENT 0")).toBeTruthy()
    expect(screen.queryByText("PAYMENT 50")).toBeNull()
    expect(screen.getByText(/1–\s*50\s*of 60/)).toBeTruthy()
    expect(asked("/api/financial/ledger-first-view")).toBe(1)
    expect(asked("/api/financial/ledger")).toBe(0)
  } finally {
    vi.useRealTimers()
  }
})

it("reads every payment for a search and searches all of them", async () => {
  show()
  await screen.findByText(/60 of 60 imported transactions/)
  fireEvent.change(screen.getByLabelText("Search payments"), { target: { value: "Needle" } })
  expect(await screen.findByText(/1 of 60 imported transactions/)).toBeTruthy()
  expect(asked("/api/financial/ledger")).toBe(1)
})

it("downloads every payment, not the page, when the CSV is asked for in the first view", async () => {
  show()
  const button = await screen.findByText("Download CSV (60)")
  act(() => fireEvent.click(button))
  await waitFor(() => expect(downloadCsv).toHaveBeenCalledTimes(1))
  const csv = String(downloadCsv.mock.calls[0][0])
  expect(csv).toContain("PAYMENT 59")
  expect(csv).toContain("PAYMENT 0")
  expect(asked("/api/financial/ledger")).toBe(1)
})

it("keeps the search box and every keystroke while the payments for a search are read", async () => {
  let release: () => void = () => {}
  const held = new Promise<void>((resolve) => (release = resolve))
  fetchAPI.mockImplementation(async (url: string) => {
    if (new URL(url, "http://test").pathname === "/api/financial/ledger") await held
    return answer(url)
  })
  show()
  await screen.findByText(/60 of 60 imported transactions/)
  const box = screen.getByLabelText("Search payments") as HTMLInputElement
  fireEvent.change(box, { target: { value: "N" } })
  // While every payment is read the box stays (the same element) and takes the rest of the word.
  expect(screen.getByLabelText("Search payments")).toBe(box)
  expect(screen.queryByText(/60 of 60 imported transactions/)).toBeNull()
  expect(screen.queryByText("PAYMENT 0")).toBeNull()
  expect(screen.getByTestId("ledger-loading")).toBeTruthy()
  fireEvent.change(box, { target: { value: "Needle" } })
  release()
  expect(await screen.findByText(/1 of 60 imported transactions/)).toBeTruthy()
  expect((screen.getByLabelText("Search payments") as HTMLInputElement).value).toBe("Needle")
})

it("says the figures are updating while the first view is read again after a change", async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <LedgerPanel caseId={CASE} investigation params={{}} />
    </QueryClientProvider>
  )
  await screen.findByText(/60 of 60 imported transactions/)
  let release: () => void = () => {}
  const held = new Promise<void>((resolve) => (release = resolve))
  fetchAPI.mockImplementation(async (url: string) => {
    if (new URL(url, "http://test").pathname === "/api/financial/ledger-first-view") await held
    return answer(url)
  })
  act(() => void client.invalidateQueries({ queryKey: ["financial-ledger", CASE] }))
  expect(await screen.findByText("Updating transactions for these filters…")).toBeTruthy()
  release()
  await waitFor(() => expect(screen.queryByText("Updating transactions for these filters…")).toBeNull())
})

it("counts nothing about a selection until every payment is read, and keeps the date range reachable", async () => {
  let release: () => void = () => {}
  const held = new Promise<void>((resolve) => (release = resolve))
  fetchAPI.mockImplementation(async (url: string) => {
    if (new URL(url, "http://test").pathname === "/api/financial/ledger") await held
    return answer(url)
  })
  show()
  await screen.findByText(/60 of 60 imported transactions/)
  // Tick one payment: the page reads every payment before it says anything about the selection.
  const [tick] = screen.getAllByRole("checkbox", { name: /select/i })
  fireEvent.click(tick)
  expect(screen.queryByText(/selected payments are (hidden|outside)/)).toBeNull()
  expect(screen.queryByText("Selected payments in this account/date range")).toBeNull()
  expect(screen.getByTestId("ledger-loading")).toBeTruthy()
  // The date range stays reachable while they are read.
  expect(screen.getAllByText(/First available date|Date range/).length).toBeGreaterThan(0)
  release()
  expect(await screen.findByText(/60 of 60 imported transactions/)).toBeTruthy()
})

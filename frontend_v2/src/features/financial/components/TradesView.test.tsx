import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import { afterEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { TradesView } from "./TradesView"

vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(),
}))
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({ canEdit: true }),
}))
afterEach(cleanup)

const caseId = "10000000-0000-4000-8000-000000000001"

function trade(overrides: Record<string, unknown> = {}) {
  return {
    id: "20000000-0000-4000-8000-000000000001",
    row_kind: "trade",
    side: "repo_maturity",
    holding_kind: null,
    operation: "Compra de Reporto Venc",
    instrument: "BPAG91 270506",
    isin: null,
    quantity: "10153",
    quantity_printed: "10,153",
    price: "101.40656389",
    currency: "MXN",
    gross_minor: 102958084,
    commission_minor: 0,
    premium_minor: 22880,
    tax_minor: 1410,
    net_minor: 102979554,
    market_value_minor: null,
    trade_date: "2025-03-31",
    settlement_date: "2025-04-01",
    as_of_date: null,
    execution_time: null,
    term_days: 1,
    rate_printed: "8.000000",
    proof_class: "p3",
    account: "Synthetic Casa de Bolsa 0001",
    file: "statement.pdf",
    evidence_file_id: "30000000-0000-4000-8000-000000000001",
    cash_transaction_id: "40000000-0000-4000-8000-000000000001",
    citation: {
      file_id: "30000000-0000-4000-8000-000000000001",
      page: 3,
      printed_text: "31 01 18500002 Compra de Reporto BPAG91 270506 0 10,153",
      cash_leg: { transaction_id: "40000000-0000-4000-8000-000000000001", amount_minor: 102979554, direction: "credit" },
    },
    not_printed: ["execution_time", "isin"],
    not_read: [],
    checks: {},
    corrections: {},
    origin: { kind: "model", text: "Read by Claude · not confirmed" },
    ...overrides,
  }
}

function view() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <TradesView caseId={caseId} />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

it("shows each trade with its instrument, quantity, dates, model label, source page and cash line, and the true count", async () => {
  vi.mocked(fetchAPI).mockImplementation(async (url) => {
    expect(String(url)).toContain(`case_id=${caseId}`)
    return { row_kind: "trade", total: 51, returned: 1, page: 1, page_size: 50, next_page: 2, items: [trade()],
             not_shown_cash_leg_not_in_ledger: 2, revision: null }
  })
  view()
  expect(await screen.findByText("BPAG91 270506")).toBeTruthy()
  expect(screen.getByText(/Showing 1–1 of 51 trades/)).toBeTruthy()
  expect(screen.getByText(/2 not shown: their cash line is no longer in the money ledger/)).toBeTruthy()
  expect(screen.getByText("10,153")).toBeTruthy()
  expect(screen.getByText("2025-03-31")).toBeTruthy()
  // Minor units scaled by the currency's exponent, exactly (never by floating point).
  expect(screen.getByText("1,029,795.54 MXN")).toBeTruthy()
  expect(screen.getByText("Read by Claude · not confirmed")).toBeTruthy()
  expect(screen.getByText(/no time of execution/)).toBeTruthy()
  const source = screen.getByRole("link", { name: /statement.pdf, page 3/ })
  expect(source.getAttribute("href")).toBe("/api/evidence/30000000-0000-4000-8000-000000000001/file#page=3")
  expect(screen.getByRole("link", { name: "Cash line" }).getAttribute("href")).toContain(
    "view=transactions&payment=40000000-0000-4000-8000-000000000001"
  )
})

it("shows a corrected value with the value as read, and sends a correction with its reason", async () => {
  const posts: unknown[] = []
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (options?.method === "POST") {
      posts.push({ url, body: options.body })
      return trade()
    }
    return { row_kind: "trade", total: 1, returned: 1, page: 1, page_size: 50, next_page: null,
             items: [trade({ quantity: "10154", corrections: { quantity: { read: "10153", value: "10154",
               reason: "page 3", by: { name: "Investigator" } } } })],
             not_shown_cash_leg_not_in_ledger: 0, revision: null }
  })
  view()
  expect(await screen.findByText("10,154")).toBeTruthy()
  expect(screen.getByText(/read 10153 · corrected by Investigator/)).toBeTruthy()
  fireEvent.click(screen.getByRole("button", { name: "Correct" }))
  fireEvent.change(screen.getByLabelText("Corrected value"), { target: { value: "10155" } })
  fireEvent.change(screen.getByLabelText("Why"), { target: { value: "As printed on page 3" } })
  fireEvent.click(screen.getByRole("button", { name: "Save correction" }))
  await waitFor(() => expect(posts).toHaveLength(1))
  expect(posts[0]).toEqual({
    url: expect.stringContaining("/api/financial/security-rows/20000000-0000-4000-8000-000000000001/correct?case_id="),
    body: { field: "quantity", value: "10155", reason: "As printed on page 3" },
  })
})

it("says plainly when the case has no trades", async () => {
  vi.mocked(fetchAPI).mockResolvedValue({ row_kind: "trade", total: 0, returned: 0, page: 1, page_size: 50,
    next_page: null, items: [], not_shown_cash_leg_not_in_ledger: 0, revision: null })
  view()
  expect(await screen.findByText(/No trades have been read in this case/)).toBeTruthy()
})

it("shows a printed line that could not be read, with its reason and printed text, and no figures", async () => {
  vi.mocked(fetchAPI).mockResolvedValue({ row_kind: "trade", total: 1, returned: 1, page: 1, page_size: 50,
    next_page: null, not_shown_cash_leg_not_in_ledger: 0, revision: null,
    items: [trade({ quantity: null, quantity_printed: null, price: null, net_minor: null, cash_transaction_id: null,
                    unread: "line not in the position layout", not_read: ["quantity", "price", "value"],
                    citation: { file_id: "30000000-0000-4000-8000-000000000001", page: 2,
                                printed_text: "+TASA M1 0 MXN 317,820 1.1349110 360,697.41" } })] })
  view()
  expect(await screen.findByText(/Line not read \(line not in the position layout\)/)).toBeTruthy()
  expect(screen.getByText(/Printed: \+TASA M1 0 MXN 317,820/)).toBeTruthy()
  expect(screen.getByText("Not read: quantity, price, value")).toBeTruthy()
  expect(screen.queryByRole("link", { name: "Cash line" })).toBeNull()
})

it("opens a cited row wherever it falls in the list, in its own kind, and says when it no longer counts", async () => {
  const urls: string[] = []
  vi.mocked(fetchAPI).mockImplementation(async (url) => {
    urls.push(String(url))
    if (String(url).includes("/security-rows/20000000-0000-4000-8000-000000000009?")) {
      return trade({ id: "20000000-0000-4000-8000-000000000009", row_kind: "holding", holding_kind: "security",
                     instrument: "+TASA M1", as_of_date: "2025-04-30", trade_date: null, net_minor: null, market_value_minor: 8842436,
                     counts: false, not_counted_because: "Its statement is no longer in the ledger." })
    }
    return { row_kind: "holding", total: 60, returned: 0, page: 1, page_size: 50, next_page: 2, items: [],
             not_shown_cash_leg_not_in_ledger: 0, not_shown_statement_not_in_ledger: 3, revision: null }
  })
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={["/x?view=trades&security=20000000-0000-4000-8000-000000000009"]}>
        <TradesView caseId={caseId} />
      </MemoryRouter>
    </QueryClientProvider>
  )
  const panel = await screen.findByRole("region", { name: "Cited row" })
  expect(panel.textContent).toContain("Cited holding: +TASA M1 · held at 2025-04-30")
  expect(panel.textContent).toContain("88,424.36 MXN")
  expect(panel.textContent).toContain("Not counted: Its statement is no longer in the ledger.")
  await waitFor(() => expect(urls.some((u) => u.includes("kind=holding"))).toBe(true))
  expect(await screen.findByText(/3 not shown: their statement is no longer in the ledger/)).toBeTruthy()
})

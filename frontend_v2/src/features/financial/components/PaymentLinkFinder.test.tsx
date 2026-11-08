import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { agentAPI } from "@/features/agent/api"
import { financialAPI } from "../api"
import { citedPaymentIds } from "../lib/link-suggestions"
import { rankSubTransactionCandidates } from "../lib/sub-transaction-suggestions"
import type { Transaction } from "../api"
import { PaymentLinkFinder } from "./PaymentLinkFinder"
import { MoneyTrailReview } from "./MoneyTrailReview"

vi.mock("@/lib/api-client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(),
}))
vi.mock("../hooks/use-financial-access", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../hooks/use-financial-access")>()),
  useFinancialAccess: () => ({ canEdit: true, canUpload: true, ready: true, error: false }),
}))
vi.mock("./AccountOwnershipReview", () => ({ AccountOwnershipReview: () => null }))
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

const uuid = (n: number) => `10000000-0000-4000-8000-${String(n).padStart(12, "0")}`
const caseId = uuid(1)
const anchorId = uuid(2)
const exact = uuid(3)
const weaker = uuid(4)
const pay = (id: string, over: Record<string, unknown> = {}) => ({
  id,
  ref_id: `TX-${id.slice(-2)}`,
  date: "2024-01-16",
  dated: true,
  direction: "credit",
  amount_minor: "82562",
  currency: "USD",
  amount: "825.62 USD",
  account_id: uuid(9),
  account_label: "Second holder · Bank B · …2222",
  from_name: "First holder",
  to_name: "Second holder",
  description: "Transfer in",
  already_linked: false,
  ...over,
})
const anchor = pay(anchorId, {
  direction: "debit",
  account_id: uuid(8),
  account_label: "First holder · Bank A · …1111",
  date: "2024-01-15",
})
const suggestions = {
  case_id: caseId,
  mode: "connected",
  anchor,
  rule: "Suggested other sides of a payment: …",
  compared: 40,
  total: 2,
  page: 1,
  page_size: 50,
  pages: 1,
  by_level: { strong: 1, moderate: 0, weak: 1, faint: 0 },
  elapsed_ms: 120,
  left_out: { words: null, common_words: null },
  candidates: [
    { ...pay(exact), level: "strong", rule: "connected_payment", gap_days: 1,
      reasons: "same amount; 1 day later; the only same-amount payment within 31 days" },
    { ...pay(weaker, { amount_minor: "83562", amount: "835.62 USD", date: "2024-02-04" }), level: "weak",
      rule: "connected_payment", gap_days: 20, reasons: "amount differs by 10.00 USD (a possible fee or charge); 20 days later" },
  ],
}
const preview = {
  case_id: caseId, kind: "transfer", input: {}, payments: [], ownership: {}, common_holders: [],
  internal_transfer: false, implied_exchange_rate: null, receipt_unallocated_minor: null, warnings: [],
  source_revision: "a".repeat(64), transfer_breakdown: null, account_context: null,
}

function mount(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>)
}

it("shows graded suggestions strongest first and links one in one click, recording the rule", async () => {
  const calls: { url: string; body?: Record<string, unknown> }[] = []
  vi.mocked(fetchAPI).mockImplementation(async (url: string, options?: { body?: unknown }) => {
    calls.push({ url, body: options?.body as Record<string, unknown> })
    if (url.startsWith("/api/financial/payment-links/suggestions")) return suggestions as never
    if (url.startsWith("/api/financial/money-trails/preview")) return preview as never
    if (url.startsWith("/api/financial/money-trails?"))
      return { id: (options?.body as { id: string }).id, case_id: caseId, kind: "transfer", revision: 1,
        active: true, status: "current", details: { ...preview, input: options?.body, payments: [] }, history: [],
        matching_entries: [], matching_entries_truncated: false } as never
    throw Error(`unexpected ${url}`)
  })
  mount(<PaymentLinkFinder caseId={caseId} anchorId={anchorId} canLink />)
  const list = await screen.findByRole("list", { name: "Suggested other sides" })
  const rows = within(list).getAllByRole("listitem")
  expect(rows[0]).toHaveTextContent("Strong")
  expect(rows[0]).toHaveTextContent("same amount; 1 day later")
  expect(rows[0]).toHaveTextContent("From First holder to Second holder")
  expect(rows[1]).toHaveTextContent("Weak")
  expect(screen.getByText(/2 suggested \(1 strong, 1 weak\)/)).toBeTruthy()
  expect(document.querySelectorAll("select, option").length).toBe(0)
  fireEvent.click(within(rows[0]).getByRole("button", { name: "Link" }))
  await screen.findByText("Linked and saved to this case.")
  const save = calls.find((c) => c.url.startsWith("/api/financial/money-trails?"))!
  expect(save.body).toMatchObject({ kind: "transfer", debit_id: anchorId, credit_id: exact, allow_fx: false })
  expect(String(save.body!.suggested_by)).toContain("connected-payment rule (strong): same amount")
  expect(calls.every((c) => !c.url.includes("case_id=") || c.url.includes(`case_id=${caseId}`))).toBe(true)
})

it("labels the agent's suggestions as a model's and links nothing until a person clicks Link", async () => {
  const calls: string[] = []
  vi.mocked(fetchAPI).mockImplementation(async (url: string) => {
    calls.push(url)
    if (url.startsWith("/api/financial/payment-links/suggestions")) return { ...suggestions, candidates: [], total: 0,
      by_level: { strong: 0, moderate: 0, weak: 0, faint: 0 } } as never
    if (url.startsWith("/api/financial/payment-links/named"))
      return { ...suggestions, mode: "named", not_found: 0, candidates: [suggestions.candidates[1]], total: 1 } as never
    throw Error(`unexpected ${url}`)
  })
  vi.spyOn(agentAPI, "sendMessage").mockResolvedValue({
    thread_id: uuid(20), run_id: uuid(21), answer: `It may have gone to [TX-04](/cases/${caseId}/financial?view=transactions&payment=${weaker}).`,
    artifacts: [], tool_trace: [], status: "completed", created_at: "2024-01-01T00:00:00Z", mandate: {} as never,
    model_info: { provider: "openai", model_id: "gpt-x", model_name: "GPT X", server: "api" },
  } as never)
  mount(<PaymentLinkFinder caseId={caseId} anchorId={anchorId} canLink />)
  await screen.findByText("No payment in this case meets a connecting rule.")
  fireEvent.change(screen.getByLabelText("Ask the case agent"), { target: { value: "where did this money go next?" } })
  fireEvent.click(screen.getByRole("button", { name: "Ask" }))
  const box = await screen.findByRole("region", { name: "Model suggestion" })
  expect(box).toHaveTextContent("Model suggestion · GPT X (openai)")
  expect(box).toHaveTextContent("not linked: a person checks and links")
  const suggested = await within(box).findByRole("list", { name: "Payments the model suggests" })
  expect(within(suggested).getAllByRole("listitem")).toHaveLength(1)
  expect(calls.some((u) => u.includes("/money-trails"))).toBe(false)
  expect(agentAPI.sendMessage).toHaveBeenCalledWith(expect.objectContaining({ caseId }))
})

it("finds the payments a model cites by their links", () => {
  expect(citedPaymentIds(`a /cases/x/financial?payment=${exact} b payment=${exact} c payment=${weaker}`)).toEqual([
    exact,
    weaker,
  ])
})

it("the link form has no dropdown of every payment of the case", async () => {
  const ledger = Array.from({ length: 30 }, (_, i) => ({
    key: uuid(100 + i), case_id: caseId, account_id: uuid(8), source_document_id: uuid(7), direction: i % 2 ? "credit" : "debit",
    description: `Payment ${i}`, ref_id: `TX-${i}`, currency: "USD", amount_minor: "100", account_type: "bank",
    account_label: "Bank A", ordering_date: "2024-01-01", running_balance_minor: null, superseded_by_id: null,
  }))
  vi.spyOn(financialAPI, "getLedgerTransactions").mockResolvedValue({
    case_id: caseId, total: ledger.length, transactions: ledger } as never)
  vi.mocked(fetchAPI).mockImplementation(async (url: string) => {
    if (url.startsWith("/api/financial/money-trails")) return { case_id: caseId, trails: [] } as never
    if (url.startsWith("/api/financial/payment-links/suggestions")) return suggestions as never
    throw Error(`unexpected ${url}`)
  })
  mount(<MoneyTrailReview caseId={caseId} transactionIds={[anchorId]} label="Link transfer or follow this payment" />)
  fireEvent.click(screen.getByRole("button", { name: "Link transfer or follow this payment" }))
  await screen.findByRole("group", { name: "Sending account’s debit" })
  await screen.findByRole("list", { name: "Suggested other sides" })
  const options = Array.from(document.querySelectorAll("option")).map((o) => o.textContent || "")
  expect(options.some((o) => o.includes("Payment "))).toBe(false)
  expect(screen.getAllByRole("combobox").length).toBeLessThanOrEqual(1) // the relationship kind only
})

it("ranks sub-transaction candidates by a stated rule and keeps every one", () => {
  const tx = (key: string, amount: number, date: string, from = "A", to = "B") =>
    ({ key, amount, currency: "USD", date, from_entity: { name: from }, to_entity: { name: to } }) as unknown as Transaction
  const parent = tx("p", 1000, "2024-01-10")
  const ranked = rankSubTransactionCandidates(parent, 600, [
    tx("far", 50, "2024-06-01", "X", "Y"),
    tx("fit", 600, "2024-01-10"),
    tx("big", 900, "2024-01-11", "X", "Y"),
  ])
  expect(ranked.map((r) => r.tx.key)).toEqual(["fit", "far", "big"]) // a fitting amount outranks a close date
  expect(ranked[0].level).toBe("strong")
  expect(ranked[0].reasons).toContain("equals the amount still unassigned")
  expect(ranked).toHaveLength(3)
})

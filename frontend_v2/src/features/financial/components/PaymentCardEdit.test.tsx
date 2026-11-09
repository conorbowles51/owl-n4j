import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { useState } from "react"
import { beforeEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import type { LedgerTransaction } from "../api"
import { paymentFixture } from "../lib/payment-fixture.test-support"
import { correctedLine, whatChanges, cardValues } from "../lib/card-edit"
import { PaymentNamingPanel } from "./PaymentNamingPanel"

vi.mock("@/lib/api-client", () => ({
  fetchAPI: vi.fn(),
  ApiError: class ApiError extends Error {
    status = 0
  },
}))
vi.mock("@/lib/protected-file", () => ({
  useProtectedObjectUrl: (url: string | null) => ({ objectUrl: url ? `blob:${url}` : null, loading: false, error: null }),
}))
vi.mock("@/components/ui/document-viewer", () => ({ DocumentViewer: () => null }))
vi.mock("@/features/auth/hooks/use-auth", () => ({
  useAuthStore: (pick: (state: { user: { name: string; username: string } }) => unknown) =>
    pick({ user: { name: "Alex Rivera", username: "alex" } }),
}))
vi.mock("../hooks/use-payment-category-library", () => ({
  usePaymentCategoryLibrary: () => ({ data: [{ name: "Travel" }, { name: "Rent" }] }),
}))

const KEY = ["financial-ledger", "case", null]

function payment(key: string, extra: Partial<LedgerTransaction> = {}): LedgerTransaction {
  return {
    ...paymentFixture,
    key,
    case_id: "case",
    amount_minor: "10000",
    currency: "USD",
    direction: "debit",
    ordering_date: "2024-03-01",
    ordering_date_source: "transaction",
    transaction_date: "2024-03-01",
    description: "WIRE OUT ACME",
    bank_reference: "R1",
    counterparty_raw: "ACME LTD",
    account_holder: "ARRENDO SERV",
    from_name: "ARRENDO SERV",
    to_name: "ACME LTD",
    category: "",
    label_version: 2,
    label_sources: { from_name: { source: "account" }, to_name: { source: "statement" } },
    locator: { kind: "page_only", page: 2 },
    ...extra,
  } as LedgerTransaction
}

const preview = (amount: string, status = "balanced") => ({
  case_id: "case",
  transaction_id: "a",
  document_revision: "a".repeat(64),
  applied: false,
  original: { key: "a", ref_id: "TX-A", source_document_id: "doc", amount_minor: "10000", currency: "USD", direction: "debit" },
  proposed: { amount_minor: amount, currency: "USD", direction: "debit", ledger_status: "admitted" },
  statement_identity: { current: { status: "balanced", delta_minor: "0" }, proposed: { status, delta_minor: status === "balanced" ? "0" : "82562" } },
  limitation: "Statement balance only",
  verification: {
    can_record: true, current_proof_class: "p2", proposed_proof_class: "p2", reservations: [],
    included_in_default_totals: true, scope: "document", reason: null,
  },
})

let balance = "balanced"
let history: object | undefined
beforeEach(() => {
  vi.resetAllMocks()
  balance = "balanced"
  history = undefined
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    const path = String(url)
    const body = options?.body as Record<string, unknown> | undefined
    if (path.includes("/correction-preview")) return preview(String(body?.amount_minor), balance)
    if (path.includes("/correction?"))
      return {
        case_id: "case", transaction_id: "a", replacement_id: "a2", replacement_ref_id: "TX-A2",
        adjudication_id: "adj", applied: true, proof_class: "p2", ledger_status: "admitted",
      }
    if (options?.method === "PUT") return { case_id: "case", updated: 1 }
    if (path.endsWith("/source?case_id=case")) return history ? { corrected_from: history } : {}
    return {
      case_id: "case", transaction_id: "a", evidence_file_id: "file", filename: "s.pdf", locator: { kind: "page_only", page: 2 },
      locator_state: "stored", page: 2, page_count: 5, last_on_page: false, found: [], text_layer: false,
    }
  })
})

/** The panel beside a list that reads the same cached ledger, as on the Transactions page. */
function Page({ readOnly }: { readOnly?: boolean }) {
  const { data } = useQuery<{ transactions: LedgerTransaction[] }>({ queryKey: KEY, queryFn: () => null as never, enabled: false })
  const rows = data!.transactions
  const [current, setCurrent] = useState(rows[0].key)
  return (
    <>
      <ol data-testid="list">
        {rows.map((row) => (
          <li key={row.key} data-testid={`row-${row.key}`}>
            {row.key} {row.to_name} {row.category} {row.amount_minor}
          </li>
        ))}
      </ol>
      <p data-testid="current">{current}</p>
      <PaymentNamingPanel caseId="case" rows={rows} queue={rows} currentId={current} onMove={setCurrent} onClose={() => {}} readOnly={readOnly} />
    </>
  )
}

function mount(readOnly = false) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  client.setQueryData(KEY, { transactions: [payment("a"), payment("b", { to_name: "OTHER" }), payment("c")], total: 3 })
  render(
    <QueryClientProvider client={client}>
      <Page readOnly={readOnly} />
    </QueryClientProvider>
  )
  return client
}

const form = () => screen.getByRole("form", { name: "Edit this payment" })

it("an editor opens edit mode on the card with the statement page still shown beside the fields", async () => {
  mount()
  fireEvent.click(await screen.findByRole("button", { name: "Edit" }))
  const edit = form()
  for (const name of ["Who did ARRENDO SERV pay? (the payee)", "Category", "Amount", "Direction", "Date", "Reference", "Printed line", "Note"])
    expect(within(edit).getByLabelText(name)).toBeTruthy()
  expect(within(edit).getByText("Statement read: ACME LTD")).toBeTruthy()
  expect(await screen.findByRole("group", { name: "Statement viewer controls" })).toBeTruthy()
})

it("a view-only user sees no Edit button", async () => {
  mount(true)
  await screen.findByRole("group", { name: "Statement viewer controls" })
  expect(screen.queryByRole("button", { name: "Edit" })).toBeNull()
})

it("Save sends the name, category and note through the label path and updates the row in place", async () => {
  mount()
  fireEvent.click(await screen.findByRole("button", { name: "Edit" }))
  fireEvent.change(screen.getByLabelText(/Who did .* pay/), { target: { value: "ACME HOLDINGS LTD" } })
  fireEvent.change(screen.getByLabelText("Category"), { target: { value: "Rent" } })
  fireEvent.change(screen.getByLabelText("Note"), { target: { value: "Name cut off on the page" } })
  fireEvent.click(screen.getByRole("button", { name: "Save" }))
  await waitFor(() => expect(screen.queryByRole("form", { name: "Edit this payment" })).toBeNull())
  const put = vi.mocked(fetchAPI).mock.calls.find(([, options]) => options?.method === "PUT")!
  expect(put[1]!.body).toEqual({
    transactions: [{ id: "a", version: 2 }],
    counterparty_name: "ACME HOLDINGS LTD",
    named_from: "statement",
    category: "Rent",
    reason: "Name cut off on the page",
  })
  expect(vi.mocked(fetchAPI).mock.calls.some(([url]) => String(url).includes("/correction"))).toBe(false)
  const list = screen.getByTestId("list")
  expect(list.children[0].textContent).toContain("ACME HOLDINGS LTD Rent")
  expect(screen.getByTestId("current").textContent).toBe("a")
})

it("an amount change says what it changes before Save, and Save records a correction that replaces the row where it stands", async () => {
  mount()
  fireEvent.click(await screen.findByRole("button", { name: "Edit" }))
  fireEvent.change(screen.getByLabelText("Amount"), { target: { value: "925.62" } })
  expect(screen.getByRole("status", { name: "What this changes" }).textContent).toContain(
    "This raises the account's money out by 825.62 USD (from 100.00 USD to 925.62 USD)."
  )
  await screen.findByText(/balances still close/)
  fireEvent.click(screen.getByRole("button", { name: "Save" }))
  await waitFor(() => expect(screen.getByTestId("current").textContent).toBe("a2"))
  const record = vi.mocked(fetchAPI).mock.calls.find(([url]) => String(url).includes("/correction?"))!
  expect(record[1]).toMatchObject({ method: "POST", body: { amount_minor: "92562", direction: "debit", expected_revision: "a".repeat(64) } })
  const list = screen.getByTestId("list")
  expect([...list.children].map((item) => item.getAttribute("data-testid"))).toEqual(["row-a2", "row-b", "row-c"])
  expect(list.children[0].textContent).toContain("92562")
})

it("refuses when the statement's balances would stop closing, unless the person marks the statement itself as wrong", async () => {
  balance = "unbalanced"
  mount()
  fireEvent.click(await screen.findByRole("button", { name: "Edit" }))
  fireEvent.change(screen.getByLabelText("Amount"), { target: { value: "925.62" } })
  expect(await screen.findByText(/no longer equals its closing balance/)).toBeTruthy()
  const save = screen.getByRole("button", { name: "Save" }) as HTMLButtonElement
  expect(save.disabled).toBe(true)
  fireEvent.click(screen.getByLabelText(/The statement itself is wrong/))
  expect(save.disabled).toBe(false)
  fireEvent.click(save)
  await waitFor(() => expect(screen.getByTestId("current").textContent).toBe("a2"))
  const record = vi.mocked(fetchAPI).mock.calls.find(([url]) => String(url).includes("/correction?"))!
  expect((record[1]!.body as { reason: string }).reason).toMatch(/marked the statement itself as wrong/)
})

it("Cancel leaves everything as it was and saves nothing; Esc cancels too", async () => {
  mount()
  fireEvent.click(await screen.findByRole("button", { name: "Edit" }))
  fireEvent.change(screen.getByLabelText("Category"), { target: { value: "Travel" } })
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }))
  expect(screen.queryByRole("form", { name: "Edit this payment" })).toBeNull()
  fireEvent.click(screen.getByRole("button", { name: "Edit" }))
  fireEvent.keyDown(screen.getByLabelText("Amount"), { key: "Escape" })
  expect(screen.queryByRole("form", { name: "Edit this payment" })).toBeNull()
  expect(screen.getByTestId("current").textContent).toBe("a")
  expect(vi.mocked(fetchAPI).mock.calls.some(([, options]) => options?.method === "PUT" || options?.method === "POST")).toBe(false)
})

it("a corrected payment keeps the statement's reading visible on the card", async () => {
  history = {
    statement_read: { amount_minor: "10000", direction: "debit", currency: "USD", transaction_date: "2024-03-01", description: "WIRE OUT ACME", bank_reference: "R1" },
    statement_ref_id: "TX-A",
    corrections: [{ actor_name: "Alex Rivera", at: "2026-11-08T22:00:00+00:00", reason: "", by_model: false }],
  }
  const client = mount()
  client.setQueryData(KEY, { transactions: [payment("a", { amount_minor: "92562" })], total: 1 })
  expect((await screen.findByTestId("card-corrected")).textContent).toBe(
    "Statement read: 100.00 USD money out · corrected by Alex Rivera, 2026-11-08"
  )
})

it("words a direction flip and a date move plainly", () => {
  const row = payment("a")
  expect(whatChanges(row, { ...cardValues(row), direction: "credit" })).toEqual([
    "This moves the payment from the account's money out to its money in: money out falls by 100.00 USD and money in rises by 100.00 USD.",
  ])
  expect(whatChanges(row, { ...cardValues(row), date: "2024-04-01" })[0]).toMatch(/^This moves the payment from 2024-03-01 to 2024-04-01/)
  expect(correctedLine(row, { statement_read: { amount_minor: "10000", direction: "debit" }, statement_ref_id: "x", corrections: [] })).toMatch(/now match/)
})

it("names the account holder on the card", async () => {
  mount()
  expect((await screen.findByTestId("card-account-holder")).textContent).toContain("Account holder: ARRENDO SERV")
})

it("a save updates the row in place without reading the whole ledger again, in both list shapes", async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const rows = [payment("a"), payment("b")]
  const FIRST = ["financial-ledger", "case", null, "first-view", 0, 50]
  client.setQueryData(FIRST, { rows, total: 2 })
  function Live() {
    // An active ledger read, as on the page: a refetch would show up as another GET /api/financial/ledger.
    const { data } = useQuery({
      queryKey: KEY,
      queryFn: () => fetchAPI<{ transactions: LedgerTransaction[] }>("/api/financial/ledger?case_id=case"),
      staleTime: Infinity,
    })
    if (!data) return null
    return <PaymentNamingPanel caseId="case" rows={data.transactions} queue={data.transactions} currentId="a" onMove={() => {}} onClose={() => {}} />
  }
  const base = vi.mocked(fetchAPI).getMockImplementation()!
  vi.mocked(fetchAPI).mockImplementation(async (url, options) =>
    String(url).startsWith("/api/financial/ledger?") ? { transactions: rows, total: 2 } : base(url, options)
  )
  render(
    <QueryClientProvider client={client}>
      <Live />
    </QueryClientProvider>
  )
  fireEvent.click(await screen.findByRole("button", { name: "Edit" }))
  fireEvent.change(screen.getByLabelText("Category"), { target: { value: "Rent" } })
  fireEvent.click(screen.getByRole("button", { name: "Save" }))
  await waitFor(() => expect(screen.queryByRole("form", { name: "Edit this payment" })).toBeNull())
  await new Promise((resolve) => setTimeout(resolve, 50))
  const reads = vi.mocked(fetchAPI).mock.calls.filter(([url]) => String(url).startsWith("/api/financial/ledger?"))
  expect(reads).toHaveLength(1)
  expect((client.getQueryData(KEY) as { transactions: LedgerTransaction[] }).transactions[0].category).toBe("Rent")
  expect((client.getQueryData(FIRST) as { rows: LedgerTransaction[] }).rows[0].category).toBe("Rent")
})

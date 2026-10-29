import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { useState } from "react"
import { beforeEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import type { LedgerTransaction } from "../api"
import { paymentFixture } from "../lib/payment-fixture.test-support"
import { cropWindow, descriptionPattern, lineBand, needsName, similarPayments, showNextPageTop } from "../lib/payment-naming"
import { PaymentNamingPanel } from "./PaymentNamingPanel"

vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
vi.mock("@/lib/protected-file", () => ({
  useProtectedObjectUrl: (url: string | null) => ({ objectUrl: url ? `blob:${url}` : null, loading: false, error: null }),
}))
vi.mock("@/components/ui/document-viewer", () => ({ DocumentViewer: () => null }))
vi.mock("@/features/auth/hooks/use-auth", () => ({
  useAuthStore: (pick: (state: { user: { name: string; username: string } }) => unknown) =>
    pick({ user: { name: "Alex Rivera", username: "alex" } }),
}))

const locator = (top: number, bottom: number) => ({
  kind: "page_rectangle",
  page: 2,
  rect: [10_000, top, 590_000, bottom],
  page_size: [600_000, 800_000],
  units: "millipoints",
  space: "pdf_displayed",
})

function payment(key: string, extra: Partial<LedgerTransaction> = {}): LedgerTransaction {
  return {
    ...paymentFixture,
    key,
    amount_minor: "150000",
    currency: "MXN",
    direction: "debit",
    description: `T17 SPEI ENVIADO BANORTE 00${key.length}1494 PAGO FACTURA`,
    from_name: "ARRENDO SERV SA DE CV",
    to_name: "",
    label_version: 0,
    label_sources: {
      from_name: { source: "account" },
      to_name: { source: "missing", reason: "Transfer line printed without a name", explanation: "BBVA prints only the bank" },
    },
    locator: locator(400_000, 410_000),
    ...extra,
  } as LedgerTransaction
}

const pageMeta = (id: string, extra = {}) => ({
  case_id: "case",
  transaction_id: id,
  evidence_file_id: "file",
  filename: "bbva-dic-2024.pdf",
  locator: locator(400_000, 410_000),
  locator_state: "stored",
  page: 2,
  page_count: 5,
  last_on_page: false,
  found: [],
  text_layer: true,
  ...extra,
})

let meta: Record<string, object> = {}
beforeEach(() => {
  vi.resetAllMocks()
  meta = {}
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (options?.method === "PUT" || options?.method === "POST")
      return { case_id: "case", updated: (options.body as { transactions: unknown[] }).transactions.length }
    const id = decodeURIComponent(String(url).split("/ledger/")[1].split("/")[0])
    return meta[id] ?? pageMeta(id)
  })
})

function Harness({ rows, start, readOnly }: { rows: LedgerTransaction[]; start: string; readOnly?: boolean }) {
  const [current, setCurrent] = useState(start)
  const [closed, setClosed] = useState(false)
  if (closed) return <p>panel closed</p>
  return (
    <>
      <p data-testid="current">{current}</p>
      <PaymentNamingPanel
        caseId="case"
        rows={rows}
        queue={rows.filter(needsName)}
        currentId={current}
        onMove={setCurrent}
        onClose={() => setClosed(true)}
        readOnly={readOnly}
        stickyTop={240}
      />
    </>
  )
}

function mount(rows: LedgerTransaction[], start = rows[0].key, readOnly = false) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  client.setQueryData(["financial-ledger", "case", null], { transactions: rows, total: rows.length })
  render(
    <QueryClientProvider client={client}>
      <Harness rows={rows} start={start} readOnly={readOnly} />
    </QueryClientProvider>
  )
  return client
}

const puts = () => vi.mocked(fetchAPI).mock.calls.filter(([, options]) => options?.method === "PUT")

it("places the highlight from the stored rectangle and shows the lines around it", async () => {
  expect(lineBand(locator(400_000, 410_000))).toEqual({ page: 2, top: 0.5, bottom: 0.5125, left: 10 / 600, right: 590 / 600 })
  const window = cropWindow({ top: 0.5, bottom: 0.5125 })
  expect(window.top).toBeCloseTo(0.45)
  expect(window.bottom).toBeCloseTo(0.5875)
  expect(showNextPageTop(lineBand(locator(400_000, 410_000)), false, 5)).toBe(false)
  expect(showNextPageTop(lineBand(locator(400_000, 410_000)), true, 5)).toBe(true)
  expect(showNextPageTop(lineBand(locator(760_000, 772_000)), false, 5)).toBe(true)
  expect(showNextPageTop(lineBand(locator(760_000, 772_000)), true, 2)).toBe(false)

  mount([payment("a")])
  const highlight = await screen.findByTestId("statement-line-highlight")
  expect(highlight.style.top).toBe("50%")
  expect(parseFloat(highlight.style.height)).toBeCloseTo(1.25)
  expect(highlight.style.left).toBe(`${(10 / 600) * 100}%`)
  expect(screen.getByRole("img", { name: /Statement page 2, this payment highlighted/ }).getAttribute("src")).toContain(
    "/api/financial/ledger/a/statement-page/2/image?case_id=case"
  )
  expect(screen.queryByRole("img", { name: /Top of statement page 3/ })).toBeNull()
  expect(screen.getByText(/Transfer line printed without a name/)).toBeTruthy()
})

it("shows the next page's top when the payment is the last one on its page", async () => {
  meta.a = pageMeta("a", { last_on_page: true })
  mount([payment("a")])
  expect(await screen.findByRole("img", { name: "Top of statement page 3" })).toBeTruthy()
})

it("marks the amount and date found on a page-only payment's page", async () => {
  meta.a = pageMeta("a", {
    locator: { kind: "page_only", page: 2 },
    found: [
      { kind: "amount", text: "1,500.00", rect: [0.7, 0.3, 0.8, 0.31] },
      { kind: "date", text: "15/01", rect: [0.05, 0.3, 0.1, 0.31] },
    ],
  })
  mount([payment("a", { locator: { kind: "page_only", page: 2 } })])
  const amount = await screen.findByTestId("statement-found-amount")
  expect(amount.style.left).toBe("70%")
  expect(screen.getByTestId("statement-found-date").style.top).toBe("30%")
  expect(screen.getByText(/1 amount, 1 date/)).toBeTruthy()
})

it("saves the typed name for exactly this payment as read from the statement, then opens the next one", async () => {
  const rows = [payment("a", { label_version: 4 }), payment("named", { to_name: "ACME", label_sources: { to_name: { source: "description" } } }), payment("b")]
  const client = mount(rows)
  const field = await screen.findByRole("combobox", { name: "Name who was paid" })
  fireEvent.change(field, { target: { value: "  GRUAS   DEL NORTE " } })
  fireEvent.keyDown(field, { key: "Enter" })
  await waitFor(() => expect(screen.getByTestId("current").textContent).toBe("b"))
  expect(puts()).toHaveLength(1)
  const [url, options] = puts()[0]
  expect(url).toBe("/api/financial/ledger/payment-labels?case_id=case")
  expect(options?.body).toEqual({ transactions: [{ id: "a", version: 4 }], counterparty_name: "GRUAS DEL NORTE", named_from: "statement" })
  const cached = client.getQueryData<{ transactions: LedgerTransaction[] }>(["financial-ledger", "case", null])!.transactions[0]
  expect(cached.to_name).toBe("GRUAS DEL NORTE")
  expect(cached.label_sources?.to_name?.source).toBe("investigator")
  expect(cached.label_sources?.to_name?.explanation).toMatch(/^Named by Alex Rivera from the statement on /)
  expect(cached.amount_minor).toBe("150000")
})

it("moves with the arrow keys and S, and closes with Escape", async () => {
  mount([payment("a"), payment("b"), payment("c")])
  const field = await screen.findByRole("combobox", { name: "Name who was paid" })
  fireEvent.keyDown(field, { key: "ArrowRight" })
  expect(screen.getByTestId("current").textContent).toBe("b")
  fireEvent.keyDown(screen.getByRole("complementary", { name: "Name payments from the statement" }), { key: "s" })
  expect(screen.getByTestId("current").textContent).toBe("c")
  fireEvent.keyDown(screen.getByRole("combobox", { name: "Name who was paid" }), { key: "ArrowLeft" })
  expect(screen.getByTestId("current").textContent).toBe("b")
  // While a name is being typed the arrows move the cursor, not the payment.
  fireEvent.change(screen.getByRole("combobox", { name: "Name who was paid" }), { target: { value: "AB" } })
  fireEvent.keyDown(screen.getByRole("combobox", { name: "Name who was paid" }), { key: "ArrowLeft" })
  expect(screen.getByTestId("current").textContent).toBe("b")
  expect(puts()).toHaveLength(0)
  fireEvent.keyDown(screen.getByRole("combobox", { name: "Name who was paid" }), { key: "Escape" })
  expect(screen.getByText("panel closed")).toBeTruthy()
})

it("offers similar payments with checkboxes and applies only the ticked ones after Apply", async () => {
  const rows = [
    payment("a", { description: "W01 TRASPASO A TERCEROS RENTA 21 DE 30 BMRCASH Ref. REFBNTC00509957" }),
    payment("b", { description: "W01 TRASPASO A TERCEROS RENTA 22 DE 30 BMRCASH Ref. REFBNTC00509957", label_version: 2 }),
    payment("c", { description: "W01 TRASPASO A TERCEROS RENTA 23 DE 30 BMRCASH Ref. REFBNTC00509957" }),
    payment("other-account", { account_id: "elsewhere", description: "W01 TRASPASO A TERCEROS RENTA 24 DE 30 BMRCASH Ref. REFBNTC00509957" }),
    payment("credit", { direction: "credit", description: "W01 TRASPASO A TERCEROS RENTA 25 DE 30 BMRCASH Ref. REFBNTC00509957" }),
  ]
  expect(descriptionPattern(rows[0].description)).toBe(descriptionPattern(rows[1].description))
  expect(similarPayments(rows[0], rows).flatMap((group) => group.rows.map((row) => row.key))).toEqual(["b", "c"])
  mount(rows)
  const field = await screen.findByRole("combobox", { name: "Name who was paid" })
  fireEvent.change(field, { target: { value: "INMOBILIARIA SOL" } })
  fireEvent.keyDown(field, { key: "Enter" })
  const offer = await screen.findByRole("region", { name: "Similar payments" })
  expect(offer.textContent).toContain("Also name 2 similar payments “INMOBILIARIA SOL”?")
  expect(puts()).toHaveLength(1)
  fireEvent.click(screen.getByRole("checkbox", { name: /RENTA 23 DE 30/ }))
  fireEvent.click(screen.getByRole("button", { name: "Apply to 1 payment" }))
  await waitFor(() => expect(puts()).toHaveLength(2))
  expect(puts()[1][1]?.body).toEqual({
    transactions: [{ id: "b", version: 2 }],
    counterparty_name: "INMOBILIARIA SOL",
    named_from: "statement",
    same_as: "a",
  })
})

it("undoes a saved name through the audited remove path", async () => {
  mount([payment("a", { label_version: 1 }), payment("b")])
  const field = await screen.findByRole("combobox", { name: "Name who was paid" })
  fireEvent.change(field, { target: { value: "ACME" } })
  fireEvent.keyDown(field, { key: "Enter" })
  fireEvent.click(await screen.findByRole("button", { name: "Undo" }))
  await waitFor(() =>
    expect(vi.mocked(fetchAPI).mock.calls.some(([url]) => String(url).startsWith("/api/financial/ledger/payment-labels/remove"))).toBe(true)
  )
  const remove = vi.mocked(fetchAPI).mock.calls.find(([url]) => String(url).includes("/remove"))!
  expect(remove[1]?.body).toEqual({ transactions: [{ id: "a", version: 2 }], fields: ["counterparty_name"] })
})

it("does not ask again about a payment a person already named or linked", () => {
  expect(needsName(payment("a"))).toBe(true)
  expect(needsName(payment("a", { label_sources: { to_name: { source: "investigator" } } }))).toBe(false)
  expect(needsName(payment("a", { to_name: "ACME" }))).toBe(false)
  expect(needsName(payment("a", { counterparty_link: { kind: "party", id: "p", label: "ACME" } }))).toBe(false)
  expect(needsName(payment("a", { direction: "credit", from_name: "", label_sources: { from_name: { source: "missing" } } }))).toBe(true)
})

it("leaves room for the sticky tools bar above it when it sits beside the table", async () => {
  mount([payment("a")])
  const panel = await screen.findByRole("complementary", { name: "Name payments from the statement" })
  expect(panel.style.getPropertyValue("--naming-top")).toBe("248px")
  expect(panel.className).toContain("xl:max-h-[calc(100vh-var(--naming-top)-8px)]")
})

it("shows a viewer the statement line and the queue with no name field, and never saves", async () => {
  mount([payment("a"), payment("b"), payment("c")], "a", true)
  const panel = await screen.findByRole("complementary", { name: "Statement lines of payments without a name" })
  expect(await screen.findByTestId("statement-line-highlight")).toBeTruthy()
  expect(screen.queryByRole("combobox")).toBeNull()
  expect(screen.queryByRole("button", { name: /Save and next/ })).toBeNull()
  expect(screen.getByText("1 of 3 without a name in view")).toBeTruthy()
  expect(screen.getByText(/Why there is no name/).parentElement?.textContent).toMatch(/Transfer line printed without a name/)
  fireEvent.keyDown(panel, { key: "ArrowRight" })
  expect(screen.getByTestId("current").textContent).toBe("b")
  fireEvent.keyDown(panel, { key: "s" })
  expect(screen.getByTestId("current").textContent).toBe("c")
  fireEvent.click(screen.getByRole("button", { name: "← Previous" }))
  expect(screen.getByTestId("current").textContent).toBe("b")
  fireEvent.keyDown(panel, { key: "Enter" })
  expect(puts()).toHaveLength(0)
  fireEvent.keyDown(panel, { key: "Escape" })
  expect(screen.getByText("panel closed")).toBeTruthy()
})

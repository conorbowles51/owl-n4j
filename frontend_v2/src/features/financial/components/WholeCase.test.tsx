import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import type { ReactNode } from "react"
import { beforeEach, expect, it, vi } from "vitest"
import { useFinancialDraftStore } from "../stores/financial-drafts"
import { WholeCasePatterns } from "./WholeCasePatterns"
import { WholeCaseProgress } from "./WholeCaseProgress"
import { WholeCaseTimeline } from "./WholeCaseTimeline"
import { WholeCaseTransfers } from "./WholeCaseTransfers"
import { WholeCasePdf } from "./WholeCasePdf"

const api = vi.hoisted(() => ({ fetchAPI: vi.fn() }))
vi.mock("@/lib/api-client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api-client")>()),
  fetchAPI: api.fetchAPI,
}))
vi.mock("./SavePaymentSelection", () => ({ SavePaymentSelection: () => null }))
vi.mock("../hooks/use-financial-access", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../hooks/use-financial-access")>()),
  useFinancialAccess: () => ({ canEdit: true, canUpload: true, ready: true, error: false }),
}))

const wrap = (node: ReactNode) =>
  render(<QueryClientProvider client={new QueryClient()}>{node}</QueryClientProvider>)
const side = (key: string) => ({ key, account_id: "a" + key, account_label: "Account " + key, ordering_date: "2024-01-02", description: "Move " + key })
const pair = (n: number, level = "weak") => ({
  debit_id: "d" + n,
  credit_id: "c" + n,
  currency: "USD",
  amount_minor: "1000",
  debit: side("d" + n),
  credit: side("c" + n),
  level,
  reasons: { match: ["same amount"], substantiation: [] },
})
function routes(run: object, pages: Record<string, unknown[]>) {
  api.fetchAPI.mockImplementation(async (url: string, options?: { method?: string }) => {
    if (options?.method === "POST") return run
    const section = decodeURIComponent(url.match(/pages\/([^?]+)/)?.[1] ?? "")
    if (!section) return run
    const offset = Number(new URL(url, "http://x").searchParams.get("offset"))
    const limit = Number(new URL(url, "http://x").searchParams.get("limit"))
    const items = pages[section] ?? []
    return { total: items.length, offset, limit, items: items.slice(offset, offset + limit) }
  })
}
beforeEach(() => {
  api.fetchAPI.mockReset()
  useFinancialDraftStore.setState({ drafts: {} })
})

it("shows which step of how many, from true counts, while a run works", () => {
  wrap(
    <WholeCaseProgress
      run={{ id: "r", kind: "transfers", status: "running", phase: "Saving the results", step: 3, steps: 3, done: 500, total: 11176, created_at: "" }}
      error={null}
      noun="comparison"
      onAgain={() => undefined}
    />
  )
  expect(screen.getByText(/Step 3 of 3: Saving the results \(500 of 11,176\)/)).toBeTruthy()
})

it("says a stopped run stopped and offers to run again", () => {
  const again = vi.fn()
  wrap(
    <WholeCaseProgress
      run={{ id: "r", kind: "timeline", status: "stopped", phase: "", step: 1, steps: 3, done: 0, total: 0, error: "The server restarted while this ran. Nothing partial was kept. Run it again.", created_at: "" }}
      error={null}
      noun="timeline"
      onAgain={again}
    />
  )
  expect(screen.getByRole("alert").textContent).toContain("Nothing partial was kept")
  fireEvent.click(screen.getByRole("button", { name: "Run the whole case again" }))
  expect(again).toHaveBeenCalled()
})

it("pages a whole-case comparison with its true counts; weak pairs stay listed", async () => {
  const graded = Array.from({ length: 30 }, (_, i) => pair(i))
  routes(
    {
      id: "a".repeat(32), kind: "transfers", status: "completed", phase: "Finished", step: 3, steps: 3, done: 1, total: 1, created_at: "",
      counts: { rows: 9804, candidates: 30, graded: 12408, reference_evidence: 0 },
      summary: { snapshot_sha256: "0".repeat(64), excluded_rows: 3, limitation: "L", rule: "R", by_level: { strong: 0, moderate: 507, weak: 5317, faint: 6584 }, left_out_words: "Not listed: possible pairs 15363 more than 365 days apart.", date_unavailable_count: 0 },
    },
    { candidates: graded, graded }
  )
  wrap(<WholeCaseTransfers caseId="case" start="" end="" population="working" tolerance={3} onSource={() => undefined} />)
  expect(await screen.findByText(/9,804 payments · 3 excluded · 30 possible pairs/)).toBeTruthy()
  expect(screen.getByText(/Every possible pair, graded \(12,408\)/)).toBeTruthy()
  expect(screen.getByText(/5,317 weak · 6,584 faint/)).toBeTruthy()
  expect(screen.getByText(/15363 more than 365 days apart/)).toBeTruthy()
  await screen.findByLabelText("Graded pair 25")
  fireEvent.click(screen.getByRole("button", { name: "Next graded pairs" }))
  await screen.findByLabelText("Graded pair 26")
  await waitFor(() => expect(screen.queryByLabelText("Graded pair 25")).toBeNull())
})

it("opens each month's count to its payments and searches them all", async () => {
  const row = (key: string) => ({ key, source_document_id: "s", account_id: "a", account_label: "Acct", chronology_date: "2024-03-02", chronology_basis: "transaction_date", ordering_date: "2024-03-02", direction: "debit", amount_minor: "500", currency: "USD", proof_class: "p3", description: "Rent " + key })
  routes(
    {
      id: "b".repeat(32), kind: "timeline", status: "completed", phase: "Finished", step: 3, steps: 3, done: 1, total: 1, created_at: "",
      counts: { rows: 9804 },
      summary: { snapshot_sha256: "0".repeat(64), excluded_rows: 0, limitation: "L", months: [{ month: "2024-03", payments: 2, credits: 0, debits: 2, totals: { USD: { credits_minor: "0", debits_minor: "1000" } } }] },
    },
    { "rows@2024-03": [row("one"), row("two")], rows: [row("one"), row("two")] }
  )
  wrap(<WholeCaseTimeline caseId="case" params={{}} population="working" events={null} onSource={() => undefined} />)
  fireEvent.click(await screen.findByRole("button", { name: "Open 2 payments in 2024-03" }))
  expect(await screen.findByText("Rent two")).toBeTruthy()
  expect(api.fetchAPI.mock.calls.some(([url]) => String(url).includes("rows%402024-03"))).toBe(true)
})

it("pages patterns by kind and opens a group above fifty to every payment", async () => {
  const source = (n: number) => ({ row: { key: "k" + n, account_label: "A", chronology_date: "2024-01-01", direction: "debit", amount_minor: "1", currency: "USD", description: "d" + n }, source: { evidence_file_id: "f" }, provenance: {} })
  const sources = Array.from({ length: 147 }, (_, i) => source(i))
  const hypothesis = { id: "h", kind: "repeated_counterparty", counterparty_label: "TRUIST MERCH SVC", transaction_ids: sources.map((s) => s.row.key), gap_days: 3, account_id: "a", account_label: "A", currency: "USD", amount_minor: "147", sources: sources.slice(0, 50), sources_total: 147, sources_start: 0, explanation: "E", limitation: "L" }
  routes(
    {
      id: "c".repeat(32), kind: "patterns", status: "completed", phase: "Finished", step: 3, steps: 3, done: 1, total: 1, created_at: "",
      counts: { hypotheses: 1267 },
      summary: { case_id: "case", reviewed_rows: 1787, date_unavailable_count: 0, limitation: "L", by_kind: { repeated_counterparty: 123, repeated_equal_amount: 746, equal_amount_in_and_out: 398 } },
    },
    { hypotheses: [hypothesis], sources }
  )
  wrap(<WholeCasePatterns caseId="case" request={{ population: "working", window_days: 3 }} onSource={() => undefined} />)
  expect(await screen.findByText(/1,787 payments checked/)).toBeTruthy()
  expect(screen.getByRole("option", { name: "Repeated names (123)" })).toBeTruthy()
  expect(await screen.findByText(/total of these 147 payments/)).toBeTruthy()
  expect(screen.getByRole("button", { name: /Save explanation/ }).hasAttribute("disabled")).toBe(true)
  expect(await screen.findByRole("button", { name: "Open payment 51" })).toBeTruthy()
})

it("lists every numbered PDF part and the download", async () => {
  routes(
    {
      id: "d".repeat(32), kind: "pdf", status: "completed", phase: "Finished", step: 3, steps: 3, done: 1, total: 1, created_at: "",
      summary: { readings: 10861, parts: 6, part_limit: 2000, archive_bytes: 2097152, listed: [{ part: 1, of: 6, filename: "p1.pdf", readings: 2000, words: "Part 1 of 6: payments 1 to 2,000 of 10,861" }] },
    },
    {}
  )
  wrap(<WholeCasePdf caseId="case" params={{}} marking="unmarked" />)
  expect(await screen.findByText(/6 numbered PDF parts cover all 10,861 captured readings/)).toBeTruthy()
  expect(screen.getByRole("link", { name: /Download all parts \(2\.0 MB\)/ })).toBeTruthy()
})

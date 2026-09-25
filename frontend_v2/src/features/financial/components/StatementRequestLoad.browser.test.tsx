import "@/styles/globals.css"
import { page } from "vitest/browser"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, cleanup, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { TooltipProvider } from "@/components/ui/tooltip"
import { fetchAPI } from "@/lib/api-client"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import { useFinancialDraftStore } from "../stores/financial-drafts"
import { useFinancialStore } from "../stores/financial.store"
import { useStatementWorkspace } from "../stores/statement-workspace"
import { FinancialPage } from "./FinancialPage"

vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()), fetchAPI: vi.fn(),
}))
vi.mock("@/features/cases/hooks/use-cases", () => ({
  useCase: () => ({ data: { id: "case", title: "Synthetic request measurement" }, isPending: false }),
}))
vi.mock("../hooks/use-financial-access", async (original) => ({
  ...(await original<typeof import("../hooks/use-financial-access")>()),
  useFinancialAccess: () => ({ canEdit: true, canUpload: true, ready: true, error: false }),
}))
vi.mock("./TransactionSourceHighlight", () => ({
  TransactionSourceHighlight: () => <div className="h-40 border p-4">Synthetic source preview</div>,
}))

const revision = "a".repeat(64)
const file = { id: "file", case_id: "case", original_filename: "Synthetic January.pdf", status: "processed" }
const proposal = {
  case_id: "case", evidence_file_id: "file", filename: file.original_filename,
  currency: "EUR", revision,
  metadata: { holder: "Example Company", account_number: "00123", institution: "Example Bank", period: "January 2026", period_start: "2026-01-01", period_end: "2026-01-31" },
  rows: [{
    id: "1:0:1", page_number: 1, table_index: 0, row_index: 1,
    source_cells: [{ column_index: 0, expected_text: "2026-01-02", locator: {} }],
    fields: { date: "2026-01-02", description: "Synthetic payment", amount_minor: "100", direction: "credit", counterparty: "Example payer" },
    issues: [], excluded: false, kind: "transaction",
  }],
  issues: [], transaction_count: 1, needs_attention: 0, page_numbers: [1],
}
type Request = { url: string; method: string; signal?: AbortSignal | null }
let requests: Request[] = []
let releaseSave: (value: unknown) => void = () => {}
let rejectSave: (reason: Error) => void = () => {}
let client: QueryClient
const reads = (path: string) => requests.filter((request) => request.url.includes(path) && request.method === "GET").length
const writes = (path: string) => requests.filter((request) => request.url.includes(path) && request.method !== "GET")
const settle = (ms: number) => act(() => new Promise<void>((resolve) => setTimeout(resolve, ms)))

beforeEach(async () => {
  localStorage.clear()
  sessionStorage.clear()
  useAuthStore.setState({ user: null })
  useFinancialStore.getState().reset()
  useFinancialDraftStore.setState({ drafts: {} })
  useStatementWorkspace.setState({ selections: {}, reviewChoices: {}, pages: {}, sectionSearches: {} })
  requests = []
  client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  vi.mocked(fetchAPI).mockReset()
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    requests.push({ url, method: options?.method || "GET", signal: options?.signal })
    if (url.includes("/progress?")) return new Promise((resolve, reject) => { releaseSave = resolve; rejectSave = reject })
    if (url.includes("/checks?")) return { revision, checks_revision: "b".repeat(64), applied: false, checks: [], admission: { status: "needs_review", can_import: false, revision: "b".repeat(64), blockers: [{ message: "Printed closing balance is not available." }] } }
    if (url.includes("/coverage-check?")) return { case_id: "case", evidence_file_id: "file", available: true, revision: "c".repeat(64), candidates: [] }
    if (options?.method) throw Error(`Unexpected mutation: ${url}`)
    if (url.startsWith("/api/evidence?")) return { files: [file] }
    if (url.startsWith("/api/evidence-upload-")) return []
    if (url.includes("/statement-import/file?")) return proposal
    if (url.includes("/statement-import/files?")) return { case_id: "case", files: [], truncated: false }
    if (url.includes("/deployment-recovery?")) return { run: null, total: 0, counts: {}, items: [] }
    if (url.includes("/ledger-categories?")) return { case_id: "case", categories: [] }
    if (url.startsWith("/api/financial?")) return { transactions: [], total: 0, dataset_mode: "transactions", uses_legacy_financial_model: false }
    if (url.includes("/categories?")) return { categories: [] }
    if (url.includes("/entities?")) return { entities: [] }
    return { case_id: "case", applied: false, offset: 0, has_more: false, limitation: "Synthetic empty scope", items: [], accounts: [], transactions: [], total: 0, runs: [], decisions: [], files: [], entries: [] }
  })
  await page.viewport(1360, 1000)
})
afterEach(() => { cleanup(); client.clear() })

function mount() {
  render(<QueryClientProvider client={client}><TooltipProvider><MemoryRouter initialEntries={["/cases/case/financial?view=statements&files=1&reviewFile=file"]}><Routes><Route path="/cases/:id/financial" element={<main className="flex h-[950px] flex-col"><FinancialPage /></main>} /></Routes></MemoryRouter></TooltipProvider></QueryClientProvider>)
}

it("measures connected review requests, saves once, and keeps edits usable after a failed save without a refetch loop", async () => {
  mount()
  await screen.findByRole("button", { name: "Save progress" })
  await waitFor(() => expect(writes("/checks?")).toHaveLength(1))
  await settle(5600)
  const baseline = {
    proposal: reads("/statement-import/file?"),
    status: reads("/statement-import/files?"),
    coverage: reads("/statement-coverage?"),
    accounts: reads("/ledger-accounts?"),
    checks: writes("/checks?").length,
    overlap: writes("/coverage-check?").length,
  }
  console.info("Synthetic 5.6s review request baseline", baseline)
  expect(baseline.proposal).toBe(1)
  expect(baseline.checks).toBe(1)
  expect(baseline.overlap).toBe(1)
  // A direct URL can briefly render the register before applying the route.
  // Hidden case-wide readers must not continue polling during a review.
  expect(baseline.status).toBeLessThanOrEqual(1)
  expect(baseline.coverage).toBe(0)
  expect(reads("/ledger-accounts?case_id=case&search=")).toBe(0)
  expect(reads("/api/evidence-upload-sessions?")).toBeLessThanOrEqual(1)
  expect(reads("/api/evidence-upload-groups?")).toBeLessThanOrEqual(1)

  await page.getByRole("button", { name: "Show corrections and import choices", exact: true }).click()
  await page.getByRole("textbox", { name: "Account holder", exact: true }).fill("Corrected Example Company")
  await waitFor(() => expect(writes("/checks?")).toHaveLength(2))
  await waitFor(() => expect(writes("/coverage-check?")).toHaveLength(2))
  expect(writes("/progress?")).toHaveLength(0)
  await page.getByRole("button", { name: "Save progress" }).click()
  await waitFor(() => expect(writes("/progress?")).toHaveLength(1))
  expect(screen.getByRole("button", { name: "Saving progress…" })).toBeDisabled()
  await settle(1200)
  expect(writes("/progress?")).toHaveLength(1)
  await act(async () => rejectSave(Error("Synthetic save failed; try again.")))
  await screen.findByText(/Synthetic save failed; try again. Your edits remain/)
  expect(screen.getByRole("button", { name: "Save progress" })).toBeEnabled()
  expect(screen.getByLabelText("Account holder")).toHaveValue("Corrected Example Company")
  await page.getByRole("button", { name: "Save progress" }).click()
  await waitFor(() => expect(writes("/progress?")).toHaveLength(2))
  await act(async () => releaseSave({
    case_id: "case", evidence_file_id: "file", review_revision: "d".repeat(64), saved_at: "2026-09-25T12:00:00Z", saved_by: { name: "Synthetic investigator" },
    request: { ...proposal.metadata, expected_revision: revision, currency: "EUR", rows: [] },
  }))
  await screen.findByText("Progress saved to the case. You can reopen this statement on another device.")
  await settle(1200)
  expect(reads("/statement-import/file?")).toBe(1)
  expect(writes("/checks?")).toHaveLength(2)
  expect(writes("/coverage-check?")).toHaveLength(2)
  expect(writes("/progress?")).toHaveLength(2)
  const statusBeforeReturn = reads("/statement-import/files?")
  await page.getByRole("button", { name: "All files & imports", exact: true }).click()
  await screen.findByRole("button", { name: `Review ${file.original_filename}` })
  await waitFor(() => expect(reads("/statement-import/files?")).toBeGreaterThan(statusBeforeReturn))
  await page.getByRole("button", { name: "Continue last statement review", exact: true }).click()
  expect(screen.getByLabelText("Account holder")).toHaveValue("Corrected Example Company")
  const statusAfterReturn = reads("/statement-import/files?")
  const recoveryAfterReturn = reads("/deployment-recovery?")
  const uploadsAfterReturn = reads("/api/evidence-upload-")
  // Imported-detail saves invalidate shared caches. A disabled hidden reader
  // should remain quiet even under that wider invalidation, while the active
  // statement still refreshes and retains its in-progress correction.
  const proposalBeforeRefresh = reads("/statement-import/file?")
  await act(() => client.invalidateQueries())
  expect(reads("/statement-import/file?")).toBe(proposalBeforeRefresh + 1)
  await settle(5600)
  expect(reads("/statement-import/files?")).toBe(statusAfterReturn)
  expect(reads("/deployment-recovery?")).toBe(recoveryAfterReturn)
  expect(reads("/api/evidence-upload-")).toBe(uploadsAfterReturn)
  expect(screen.getByLabelText("Account holder")).toHaveValue("Corrected Example Company")
  expect(writes("/progress?")).toHaveLength(2)
  await page.getByRole("button", { name: "Review accounts", exact: true }).click()
  await waitFor(() => expect(reads("/statement-coverage?")).toBe(1))
  expect(reads("/ledger-accounts?case_id=case&search=")).toBe(1)
  console.info("Synthetic review total requests", requests.map(({ url, method }) => `${method} ${url}`))
}, 30000)

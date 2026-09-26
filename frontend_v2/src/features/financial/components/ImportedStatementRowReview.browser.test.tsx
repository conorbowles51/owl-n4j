import "@/styles/globals.css"
import "../financial-workspace.css"
import { page } from "vitest/browser"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import { financialDraftKey, useFinancialDraftStore } from "../stores/financial-drafts"
import { useInvestigationScopeStore } from "../stores/investigation-scope"
import { paymentTableDraftName, emptyPaymentTableView } from "../lib/payment-table-draft"
import { useStatementWorkspace } from "../stores/statement-workspace"
import { financialAPI } from "../api"
import { paymentFixture } from "../lib/payment-fixture.test-support"
import { StatementImportPanel } from "./StatementImportPanel"

vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(),
}))
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({
    canEdit: true,
    canUpload: false,
    ready: true,
    error: false,
  }),
}))
vi.mock("./TransactionSourceHighlight", () => ({
  TransactionSourceHighlight: () => (
    <div className="h-32 border p-3">
      Synthetic PDF: debit 12.34; remaining balance 987.66.
    </div>
  ),
}))
const revision = "a".repeat(64),
  rowId = "1:0:2"
const warning =
  "Check which deposit or withdrawal column contains this payment."
const source = {
  case_id: "case",
  evidence_file_id: "file",
  filename: "Synthetic column review.pdf",
  currency: "EUR",
  revision,
  metadata: {
    holder: "Example Company",
    account_number: "00123",
    institution: "Example Bank",
    period: "April 2026",
    period_start: "2026-04-01",
    period_end: "2026-04-30",
  },
  rows: [
    {
      id: rowId,
      kind: "transaction",
      excluded: false,
      page_number: 1,
      table_index: 0,
      row_index: 2,
      fields: {
        date: "2026-04-15",
        description: "SYNTHETIC TAX PAYMENT",
        amount_minor: "1234",
        direction: "debit",
        balance: "98766",
      },
      source_cells: [
        {
          column_index: 0,
          expected_text: "15/ABR SYNTHETIC TAX PAYMENT 12.34 987.66",
          locator: { kind: "page_only", page: 1 },
        },
      ],
      issues: [warning],
    },
  ],
  issues: [],
  transaction_count: 1,
  needs_attention: 1,
  page_numbers: [1],
}

let client: QueryClient
let stored = {
  ...paymentFixture,
  key: "saved-payment",
  source_document_id: "saved-source",
  amount_minor: "1234",
  direction: "debit",
  description: "SYNTHETIC TAX PAYMENT",
  currency: "EUR",
  proof_class: "p2",
}
afterEach(() => {
  cleanup()
  client?.clear()
  vi.restoreAllMocks()
})
it.each([1280, 390])(
  "opens correction beside an imported flagged reading and retains save, failure and return at %ipx",
  async (width) => {
    sessionStorage.clear()
    localStorage.clear()
    useAuthStore.setState({ user: null })
    useFinancialDraftStore.setState({ drafts: {} })
    useInvestigationScopeStore.getState().reset()
    useInvestigationScopeStore.getState().apply("case", { accountId: "unrelated-account" })
    const categoryKey = financialDraftKey("case", "investigation-category")
    const viewKey = financialDraftKey("case", paymentTableDraftName())
    useFinancialDraftStore.getState().put(categoryKey, "Unrelated category")
    useFinancialDraftStore.getState().put(viewKey, { ...emptyPaymentTableView, search: "Unrelated search", currency: "USD" })
    useStatementWorkspace.setState({
      selections: {},
      pages: {},
      reviewChoices: {},
      sectionSearches: {},
    })
    useStatementWorkspace.getState().select("anonymous:case", "file")
    stored = { ...stored, key: "saved-payment", amount_minor: "1234" }
    const writes: string[] = []
    let fail = true
    vi.spyOn(financialAPI, "getLedgerTransactions").mockImplementation(
      async (params) => {
        expect(params.sourceDocumentId).toBe("saved-source")
        return { case_id: "case", transactions: [stored], total: 1 }
      }
    )
    vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
      if (url.startsWith("/api/evidence?"))
        return {
          files: [
            {
              id: "file",
              case_id: "case",
              original_filename: source.filename,
              status: "processed",
            },
          ],
        }
      if (url.includes("/statement-import/file?") && !options?.method)
        return {
          ...source,
          current_import: {
            source_document_id: "saved-source",
            evidence_file_id: "file",
            revision,
            transaction_count: 1,
            currency: "EUR",
          },
        }
      if (url.includes("/payment-categories")) return { categories: [] }
      if (url.includes("/coverage-check?"))
        return {
          case_id: "case",
          evidence_file_id: "file",
          available: true,
          revision,
          candidates: [],
        }
      if (url.includes("/details?"))
        return {
          case_id: "case",
          source_document_id: "saved-source",
          evidence_file_id: "file",
          revision,
          currency: "EUR",
          pages: [1],
          account_id: "account",
          period_id: "period",
          balance_convention: "asset_balance",
          details: {
            holder: "Example Company",
            account_number: "00123",
            institution: "Example Bank",
          },
          balances: {
            opening: { amount_minor: null, page: null },
            closing: { amount_minor: null, page: null },
          },
        }
      if (url.includes("/correction-preview?")) {
        const proposed = options!.body as {
          amount_minor: string
          direction: string
        }
        return {
          case_id: "case",
          transaction_id: stored.key,
          document_revision: revision,
          applied: false,
          original: stored,
          proposed: { ...proposed, currency: "EUR", ledger_status: "admitted" },
          statement_identity: null,
          limitation: "Synthetic source comparison",
          verification: {
            can_record: true,
            current_proof_class: "p2",
            proposed_proof_class: "p2",
            reservations: [],
            included_in_default_totals: true,
            scope: "document",
            reason: null,
          },
        }
      }
      if (url.includes("/correction?")) {
        if (fail) throw Error("Synthetic save interrupted")
        writes.push(url)
        stored = { ...stored, key: "corrected-payment", amount_minor: "1200" }
        return {
          case_id: "case",
          transaction_id: "saved-payment",
          replacement_id: stored.key,
          replacement_ref_id: "TX-CORRECTED",
          adjudication_id: "event",
          applied: true,
          proof_class: "p2",
          ledger_status: "admitted",
        }
      }
      throw Error(`Unexpected request ${url}`)
    })
    client = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })
    const mount = () =>
      render(
        <QueryClientProvider client={client}>
          <MemoryRouter>
            <main className="p-4">
              <StatementImportPanel caseId="case" onImported={() => {}} />
            </main>
          </MemoryRouter>
        </QueryClientProvider>
      )
    await page.viewport(width, 950)
    mount()
    await screen.findByRole("button", { name: "Review or fix saved records" })
    await page
      .getByRole("button", { name: "Review or fix saved records", exact: true })
      .click()
    const panel = () =>
      screen.getByRole("region", {
        name: "Saved records for this flagged reading",
      })
    expect(panel()).toHaveFocus()
    await page
      .getByRole("region", { name: "Saved records for this flagged reading" })
      .getByRole("button", { name: /Correct/ })
      .click()
    const amount = await screen.findByLabelText("Proposed amount (EUR)")
    expect(amount).toHaveValue("12.34")
    await page
      .getByLabelText("Proposed amount (EUR)", { exact: true })
      .fill("12.00")
    await page
      .getByLabelText("Reason for correction", { exact: true })
      .fill("Checked against synthetic original")
    await page
      .getByRole("button", { name: "Preview correction", exact: true })
      .click()
    await page
      .getByRole("button", { name: "Record correction", exact: true })
      .click()
    await screen.findByText(/The correction could not be confirmed/)
    expect(amount).toHaveValue("12.00")
    await page
      .getByRole("button", { name: "Close correction", exact: true })
      .click()
    await page
      .getByRole("region", { name: "Saved records for this flagged reading" })
      .getByRole("button", { name: /Correct/ })
      .click()
    expect(await screen.findByLabelText("Proposed amount (EUR)")).toHaveValue(
      "12.00"
    )
    fail = false
    await page
      .getByRole("button", { name: "Preview correction", exact: true })
      .click()
    await page
      .getByRole("button", { name: "Record correction", exact: true })
      .click()
    await waitFor(() => expect(writes).toHaveLength(1))
    await page.screenshot({
      path: `/private/tmp/loupe-imported-flag-${width}.png`,
      element: panel(),
    })
    await page
      .getByRole("button", { name: "Return to original row", exact: true })
      .click()
    expect(
      screen.getByRole("button", { name: "Review or fix saved records" })
    ).toHaveFocus()
    expect(
      screen.getByText(`Original extraction flag: ${warning}`)
    ).toBeVisible()
    cleanup()
    client.clear()
    mount()
    await screen.findByRole("button", { name: "Review or fix saved records" })
    await page
      .getByRole("button", { name: "Review or fix saved records", exact: true })
      .click()
    await page
      .getByRole("region", { name: "Saved records for this flagged reading" })
      .getByRole("button", { name: /Correct/ })
      .click()
    expect(await screen.findByLabelText("Proposed amount (EUR)")).toHaveValue(
      "12.00"
    )
    expect(writes).toHaveLength(1)
    expect(useInvestigationScopeStore.getState().scopes.case.accountId).toBe("unrelated-account")
    expect(useFinancialDraftStore.getState().drafts[categoryKey]).toBe("Unrelated category")
    expect(useFinancialDraftStore.getState().drafts[viewKey]).toMatchObject({ search: "Unrelated search", currency: "USD" })
  }
)

import "@/styles/globals.css"
import { page } from "vitest/browser"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import { expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import { useStatementWorkspace } from "../stores/statement-workspace"
import { useFinancialDraftStore } from "../stores/financial-drafts"
import { StatementImportPanel } from "./StatementImportPanel"

vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(),
}))
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({ canEdit: true, canUpload: true, ready: true }),
}))
vi.mock("../hooks/use-statement-coverage-review", async (original) => ({
  ...(await original<
    typeof import("../hooks/use-statement-coverage-review")
  >()),
  useStatementCoverageReview: () => ({
    data: { available: true, candidates: [], revision: "d".repeat(64) },
    pending: false,
    retry: vi.fn(),
  }),
}))
vi.mock("../hooks/use-statement-checks", async (original) => ({
  ...(await original<typeof import("../hooks/use-statement-checks")>()),
  useStatementChecks: () => ({
    checks: [],
    pending: false,
    revision: "c".repeat(64),
    retry: vi.fn(),
  }),
}))
vi.mock("./PdfReviewIntake", () => ({ PdfReviewIntake: () => null }))
vi.mock("./TransactionSourceHighlight", () => ({
  TransactionSourceHighlight: () => (
    <div className="rounded border bg-white text-black p-5 min-h-44">
      <h2>Synthetic bank statement</h2>
      <p>The original source stays beside the saved statement controls.</p>
    </div>
  ),
}))

it.each([
  [1280, false],
  [390, false],
  [390, true],
] as const)(
  "keeps replacement blocked until saved controls reconcile, then reopens at %spx (currency recheck: %s)",
  async (width, currencyConflict) => {
    await page.viewport(width, 900)
    sessionStorage.clear()
    document.documentElement.classList.remove("dark")
    useAuthStore.setState({ user: null })
    useFinancialDraftStore.setState({ drafts: {} })
    useStatementWorkspace.setState({
      selections: {},
      reviewChoices: {},
      pages: {},
      sectionSearches: {},
    })
    useStatementWorkspace.getState().select("anonymous:case", "file")
    let corrected = false
    let rechecked = !currencyConflict
    const currency = currencyConflict ? "JPY" : "EUR"
    const imported = vi.fn(),
      writes: unknown[] = []
    const metadata = {
      holder: "Synthetic company",
      account_number: "TEST-001",
      institution: "Synthetic bank",
      period: "January 2026",
      period_start: "2026-01-01",
      period_end: "2026-01-31",
    }
    const admission = () => ({
      can_import: corrected,
      status: corrected ? "reconciled" : "needs_review",
      blockers: corrected
        ? []
        : [
            {
              message:
                "The payments do not add up to the saved closing balance.",
              kind: "arithmetic",
            },
          ],
      calculation: {
        available: true,
        currency,
        opening_minor: "0",
        credit_minor: "1000",
        debit_minor: "0",
        calculated_closing_minor: "1000",
        printed_closing_minor: corrected ? "1000" : "2000",
        difference_minor: corrected ? "0" : "-1000",
      },
    })
    const details = () => ({
      case_id: "case",
      evidence_file_id: "file",
      source_document_id: "saved",
      account_id: "account",
      period_id: "period",
      revision: (corrected ? "e" : "b").repeat(64),
      currency,
      balance_convention: "asset_balance",
      details: metadata,
      pages: [1],
      has_payment_readings: true,
      balances: {
        opening: { amount_minor: "0", page: 1 },
        closing: { amount_minor: corrected ? "1000" : "2000", page: 1 },
      },
    })
    vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
      if (url.startsWith("/api/evidence?"))
        return {
          files: [
            {
              id: "file",
              case_id: "case",
              original_filename: "Synthetic replacement.pdf",
              status: "processed",
            },
          ],
        } as never
      if (url.includes("/details?")) {
        if (options?.method === "PUT") {
          expect(options.body).toMatchObject({
            closing: { amount_minor: "1000", page: 1 },
            holder: metadata.holder,
            account_number: metadata.account_number,
          })
          writes.push(options.body)
          corrected = true
        }
        return details() as never
      }
      if (url.includes("/refresh-reading?")) {
        expect(corrected).toBe(true)
        expect(options?.body).toMatchObject({
          expected_revision: "e".repeat(64),
          currency,
        })
        writes.push(options?.body)
        return {
          case_id: "case",
          evidence_file_id: "file",
          source_document_id: "replacement",
          account_id: "account",
          transaction_count: 1,
          record_count: 1,
          incomplete_count: 0,
          applied: true,
        } as never
      }
      if (url.includes("currency=JPY")) rechecked = true
      return {
        case_id: "case",
        evidence_file_id: "file",
        filename: "Synthetic replacement.pdf",
        currency,
        revision: "a".repeat(64),
        page_numbers: [1],
        statement_page_numbers: [1],
        metadata,
        transaction_count: 1,
        needs_attention: 0,
        issues: [],
        rows: [
          {
            id: "1:0:1",
            page_number: 1,
            table_index: 0,
            row_index: 1,
            kind: "transaction",
            excluded: false,
            fields: {
              date: "2026-01-02",
              description: "Synthetic receipt",
              counterparty: "Synthetic payer",
              amount_minor: "1000",
              direction: "credit",
            },
            issues: [],
            source_cells: [
              {
                column_index: 0,
                expected_text: "2026-01-02 Synthetic receipt 10.00",
                locator: { kind: "page_only", page: 1 },
              },
            ],
          },
        ],
        current_import: {
          source_document_id: "saved",
          account_id: "account",
          evidence_file_id: "file",
          revision: (corrected ? "e" : "b").repeat(64),
          transaction_count: 0,
          details: metadata,
          currency,
          refresh_currency_conflict: rechecked
            ? null
            : {
                saved_currency: "JPY",
                reading_currency: "EUR",
                message:
                  "Your saved statement was corrected to JPY. This reading uses EUR; review its currency before replacing the saved import.",
              },
          refresh_available: rechecked,
          refresh_transaction_count: 1,
          refresh_requires_reconciliation: true,
          refresh_admission: admission(),
        },
      } as never
    })
    const mount = () =>
      render(
        <QueryClientProvider
          client={
            new QueryClient({ defaultOptions: { queries: { retry: false } } })
          }
        >
          <main className="bg-background text-foreground p-4">
            <StatementImportPanel caseId="case" onImported={imported} />
          </main>
        </QueryClientProvider>
      )
    const mounted = mount()
    if (currencyConflict) {
      const conflict = await screen.findByRole("region", {
        name: "Replacement currency review",
      })
      expect(within(conflict).getByText(/corrected to JPY/)).toBeVisible()
      expect(
        screen.queryByRole("button", {
          name: "Save 1 payments to Transactions",
        })
      ).not.toBeInTheDocument()
      conflict.scrollIntoView({ block: "start", behavior: "instant" })
      await page.screenshot({
        element: conflict,
        path: "/private/tmp/loupe-replacement-currency-conflict-390.png",
      })
      fireEvent.click(
        within(conflict).getByRole("button", {
          name: "Check this reading in saved JPY",
        })
      )
      await waitFor(() =>
        expect(
          screen.queryByRole("region", { name: "Replacement currency review" })
        ).not.toBeInTheDocument()
      )
      await waitFor(() =>
        expect(
          screen.getByRole("region", { name: "Recorded statement import" })
        ).toHaveFocus()
      )
      expect(writes).toHaveLength(0)
      expect(imported).not.toHaveBeenCalled()
    }
    const checks = await screen.findByRole("region", {
      name: "Replacement reading checks",
    })
    const saveName = "Save 1 payments to Transactions"
    expect(
      within(checks).getByRole("button", { name: saveName })
    ).toBeDisabled()
    expect(
      within(checks).getByText(
        currencyConflict
          ? /1000 JPY short of the saved closing balance/
          : /10.00 EUR short of the saved closing balance/
      )
    ).toBeVisible()
    expect(
      screen.getByText(/replacement reading still needs review/)
    ).toBeVisible()
    expect(
      screen.queryByText(/Use Save payments above/)
    ).not.toBeInTheDocument()
    fireEvent.click(within(checks).getByRole("button", { name: saveName }))
    expect(writes).toHaveLength(0)
    checks.scrollIntoView({ block: "start", behavior: "instant" })
    await page.screenshot({
      element: checks,
      path: `/private/tmp/loupe-replacement-blocked-${width}-${currency}.png`,
    })
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }))
    fireEvent.click(
      within(checks).getByRole("button", {
        name: "Review saved details and balances",
      })
    )
    await waitFor(() =>
      expect(screen.getByLabelText("Saved opening balance")).toHaveFocus()
    )
    fireEvent.change(screen.getByLabelText("Saved closing balance"), {
      target: { value: currencyConflict ? "1000" : "10.00" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }))
    await waitFor(() =>
      expect(screen.getByRole("button", { name: saveName })).toBeEnabled()
    )
    expect(writes).toHaveLength(1)
    expect(imported).not.toHaveBeenCalled()
    mounted.unmount()
    mount()
    await waitFor(() =>
      expect(screen.getByRole("button", { name: saveName })).toBeEnabled()
    )
    expect(await screen.findByLabelText("Saved closing balance")).toHaveValue(
      currencyConflict ? "1000" : "10.00"
    )
    const ready = screen.getByRole("region", {
      name: "Replacement reading checks",
    })
    expect(
      within(ready).getByText(
        "The replacement reading reconciles with your saved controls."
      )
    ).toBeVisible()
    ready.scrollIntoView({ block: "start", behavior: "instant" })
    await page.screenshot({
      element: ready,
      path: `/private/tmp/loupe-replacement-ready-${width}-${currency}.png`,
    })
    expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(width)
    fireEvent.click(within(ready).getByRole("button", { name: saveName }))
    await waitFor(() =>
      expect(imported).toHaveBeenCalledWith(
        expect.objectContaining({
          source_document_id: "replacement",
          transaction_count: 1,
        })
      )
    )
    expect(writes).toHaveLength(2)
  }
)

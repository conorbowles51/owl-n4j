import "@/styles/globals.css"
import { page } from "vitest/browser"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
  waitFor,
} from "@testing-library/react"
import { expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { StatementImportPanel } from "./StatementImportPanel"
import { useStatementWorkspace } from "../stores/statement-workspace"
import { useAuthStore } from "@/features/auth/hooks/use-auth"

vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(),
}))
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({
    canEdit: true,
    canUpload: true,
    ready: true,
    error: false,
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
vi.mock("./TransactionSourceHighlight", () => ({
  TransactionSourceHighlight: () => (
    <div className="min-h-64 border p-5">
      Synthetic Monex statement · separate peso and euro balance summaries
    </div>
  ),
}))
vi.mock("./PdfReviewIntake", () => ({ PdfReviewIntake: () => null }))

it("chooses the currency account, saves balances, switches accounts and reopens the saved state", async () => {
  await page.viewport(1280, 900)
  sessionStorage.clear()
  useAuthStore.setState({ user: null })
  useStatementWorkspace.setState({
    selections: {},
    reviewChoices: {},
    pages: {},
    sectionSearches: {},
  })
  const choices = ["MXN", "EUR"].map((currency, i) => ({
    id: currency,
    currency,
    institution: "Monex",
    account_reference: "7654321",
    period_start: "2026-05-01",
    period_end: "2026-05-31",
    page_numbers: [i + 2],
    checks: {
      balance_status: "matches",
      flagged_rows: 0,
      transaction_count: 0,
    },
  }))
  const saved = new Set<string>()
  const requests: Record<string, unknown>[] = []
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (url.startsWith("/api/evidence?"))
      return {
        files: [
          {
            id: "file",
            case_id: "case",
            original_filename: "Example Monex.pdf",
            status: "processed",
          },
        ],
      } as never
    if (url.includes("/confirm?")) {
      const body = options!.body as Record<string, unknown>
      requests.push(body)
      saved.add(body.statement_id as string)
      return {
        case_id: "case",
        evidence_file_id: "file",
        source_document_id: `source-${body.statement_id}`,
        account_id: `account-${body.statement_id}`,
        transaction_count: 0,
        incomplete_count: 0,
        applied: true,
      } as never
    }
    if (url.includes("/details?")) {
      const currency = url.includes("source-MXN") ? "MXN" : "EUR"
      const balance = {
        amount_minor: currency === "MXN" ? "32145" : "79",
        page: currency === "MXN" ? 2 : 3,
      }
      return {
        case_id: "case",
        source_document_id: `source-${currency}`,
        evidence_file_id: "file",
        account_id: `account-${currency}`,
        period_id: `period-${currency}`,
        revision: "b".repeat(64),
        currency,
        balance_convention: "asset_balance",
        details: {
          holder: "Example Services",
          account_number: "7654321",
          institution: "Monex",
          period_start: "2026-05-01",
          period_end: "2026-05-31",
        },
        pages: [1, 2, 3, 4, 5, 6],
        balances: { opening: balance, closing: balance },
      } as never
    }
    const currency =
      new URL(url, "http://localhost").searchParams.get("statement_id") || ""
    const amount = currency === "MXN" ? "32145" : "79"
    const metadata = {
      period: "May 2026",
      holder: "Example Services",
      account_number: "7654321",
      institution: "Monex",
      period_start: "2026-05-01",
      period_end: "2026-05-31",
      balance_convention: "asset_balance",
    }
    return {
      case_id: "case",
      evidence_file_id: "file",
      filename: "Example Monex.pdf",
      revision: "a".repeat(64),
      currency,
      detected_currency: currency,
      metadata,
      statement_choices: choices,
      statement_id: currency || null,
      needs_attention: 0,
      transaction_count: 0,
      can_import_balances: true,
      issues: [],
      page_numbers: [1, 2, 3, 4, 5, 6],
      rows: currency
        ? ["Opening", "Closing"].map((role, i) => ({
            id: `2:0:${i}`,
            page_number: 2,
            table_index: 0,
            row_index: i,
            kind: "balance",
            excluded: true,
            issues: [],
            source_cells: [
              {
                column_index: 0,
                expected_text: `${role} balance`,
                locator: {},
              },
            ],
            fields: { description: `${role} Balance`, balance: amount },
          }))
        : [],
      current_import: saved.has(currency)
        ? {
            source_document_id: `source-${currency}`,
            evidence_file_id: "file",
            account_id: `account-${currency}`,
            filename: "Example Monex.pdf",
            revision: "b".repeat(64),
            transaction_count: 0,
            incomplete_count: 0,
            currency,
            details: metadata,
          }
        : null,
    } as never
  })
  const mount = () =>
    render(
      <QueryClientProvider
        client={
          new QueryClient({
            defaultOptions: { queries: { retry: false, staleTime: 0 } },
          })
        }
      >
        <main className="p-4 bg-background text-foreground">
          <StatementImportPanel caseId="case" onImported={vi.fn()} />
        </main>
      </QueryClientProvider>
    )
  mount()
  fireEvent.click(screen.getByRole("button", { name: "Import a statement" }))
  await screen.findByRole("option", { name: "Example Monex.pdf" })
  fireEvent.change(screen.getByLabelText("Uploaded statement"), {
    target: { value: "file" },
  })
  await screen.findByRole("heading", { name: "This PDF contains 2 statements" })
  const accountSelect = screen.getByLabelText("Statement account")
  const mxn = within(accountSelect).getByRole("option", {
    name: "Monex · 7654321 · MXN",
  }) as HTMLOptionElement
  const eur = within(accountSelect).getByRole("option", {
    name: "Monex · 7654321 · EUR",
  }) as HTMLOptionElement
  fireEvent.change(accountSelect, { target: { value: mxn.value } })
  await screen.findAllByText(
    /This statement records balances and no transactions/
  )
  expect(screen.getByLabelText("Currency for this statement")).toHaveValue(
    "MXN"
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Show corrections and import choices" })
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Save statement balances" })
  )
  await waitFor(() => expect(requests).toHaveLength(1))
  expect(requests[0]).toMatchObject({
    currency: "MXN",
    statement_id: "MXN",
    rows: [
      { balance_minor: "32145", excluded: true },
      { balance_minor: "32145", excluded: true },
    ],
  })
  cleanup()
  mount()
  fireEvent.click(screen.getByRole("button", { name: "Import a statement" }))
  await screen.findByText(/This period’s account and balances are saved/)
  fireEvent.change(screen.getByLabelText("Statement account"), {
    target: { value: eur.value },
  })
  await screen.findAllByText(
    /This statement records balances and no transactions/
  )
  expect(screen.getByLabelText("Currency for this statement")).toHaveValue(
    "EUR"
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Show corrections and import choices" })
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Save statement balances" })
  )
  await waitFor(() => expect(requests).toHaveLength(2))
  expect(requests[1]).toMatchObject({
    currency: "EUR",
    statement_id: "EUR",
    rows: [
      { balance_minor: "79", excluded: true },
      { balance_minor: "79", excluded: true },
    ],
  })
  cleanup()
  mount()
  fireEvent.click(screen.getByRole("button", { name: "Import a statement" }))
  await screen.findByText(/This period’s account and balances are saved/)
  fireEvent.change(screen.getByLabelText("Statement account"), {
    target: { value: mxn.value },
  })
  await screen.findByText(/This period’s account and balances are saved/)
  expect(requests).toHaveLength(2)
  await screen.findAllByText(/321.45/)
  expect(screen.queryByRole("alert")).toBeNull()
  await page.screenshot({ path: "/tmp/loupe-monex-workflow.png" })
  cleanup()
})

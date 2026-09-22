import "@/styles/globals.css"
import { page } from "vitest/browser"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import { useStatementWorkspace } from "../stores/statement-workspace"
import { BatchReviewContext } from "../lib/batch-review-context"
import { StatementImportPanel } from "./StatementImportPanel"
import { ImportedRecordsPanel } from "./ImportedRecordsPanel"
import { useState } from "react"

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
    <div className="border bg-white text-slate-800 p-6 space-y-5 min-h-60">
      <h2 className="text-xl font-semibold">Example balance statement</h2>
      <p>Synthetic PDF placeholder for testing the review controls.</p>
      <p>Opening balance EUR 1,817.77</p>
      <p>Closing balance EUR 1,817.77</p>
    </div>
  ),
}))

it("leads from the missing-balance check to labelled inputs and saves without importing payments", async () => {
  await page.viewport(1360, 960)
  document.documentElement.classList.remove("dark")
  sessionStorage.clear()
  useAuthStore.setState({ user: null })
  useStatementWorkspace.setState({
    selections: {},
    reviewChoices: {},
    pages: {},
    sectionSearches: {},
  })
  useStatementWorkspace.getState().select("anonymous:case", "file")
  const saved = vi.fn(),
    save = vi.fn().mockResolvedValue({ status: "ready" })
  vi.mocked(fetchAPI).mockResolvedValue({
    case_id: "case",
    evidence_file_id: "file",
    filename: "Example balances.pdf",
    currency: "EUR",
    revision: "a".repeat(64),
    page_numbers: [1],
    statement_page_numbers: [1],
    metadata: {
      holder: "Example company",
      account_number: "0012345",
      institution: "Example bank",
      period: "January 2021",
      period_start: "2021-01-01",
      period_end: "2021-01-31",
    },
    rows: [
      {
        id: "1:0:0",
        page_number: 1,
        table_index: 0,
        row_index: 0,
        kind: "unclassified",
        excluded: true,
        fields: {},
        issues: [],
        source_cells: [
          {
            column_index: 0,
            expected_text: "Example account information",
            locator: { kind: "page_only", page: 1 },
          },
        ],
      },
    ],
    issues: [],
    transaction_count: 0,
    needs_attention: 0,
  } as never)
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <BatchReviewContext.Provider value={{ save, saved }}>
        <main className="p-5 bg-background text-foreground">
          <StatementImportPanel caseId="case" onImported={vi.fn()} />
        </main>
      </BatchReviewContext.Provider>
    </QueryClientProvider>
  )
  await screen.findByText("Review Example balances.pdf")
  expect(
    screen.getByRole("button", { name: "Save statement balances" })
  ).toBeDisabled()
  fireEvent.click(screen.getByRole("button", { name: "Show items to check" }))
  expect(
    screen.getByRole("button", { name: "Add opening balance" })
  ).toHaveFocus()
  for (const role of ["opening", "closing"]) {
    fireEvent.click(screen.getByRole("button", { name: `Add ${role} balance` }))
    const input = screen.getByLabelText(`Statement ${role} balance`)
    await waitFor(() => expect(input).toHaveFocus())
    fireEvent.change(input, { target: { value: "1817.77" } })
  }
  screen
    .getByRole("group", { name: "Statement balances" })
    .scrollIntoView({ block: "center", behavior: "instant" })
  await page.screenshot({ path: "/tmp/statement-balances-review-light.png" })
  fireEvent.click(
    screen.getByRole("button", { name: "Save statement balances" })
  )
  await waitFor(() => expect(saved).toHaveBeenCalledOnce())
  expect(save).toHaveBeenCalledWith(
    expect.objectContaining({
      rows: expect.arrayContaining([
        expect.objectContaining({
          id: "manual:opening-balance",
          excluded: true,
          balance_minor: "181777",
          manual_page: 1,
        }),
        expect.objectContaining({
          id: "manual:closing-balance",
          excluded: true,
          balance_minor: "181777",
          manual_page: 1,
        }),
      ]),
    })
  )
  expect(
    vi.mocked(fetchAPI).mock.calls.some(([url]) => url.includes("/confirm?"))
  ).toBe(false)
})

it("replaces false incomplete readings with saved zero balances and clears the Transactions warning", async () => {
  await page.viewport(1280, 900)
  sessionStorage.clear()
  useAuthStore.setState({ user: null })
  useStatementWorkspace.setState({
    selections: {},
    reviewChoices: {},
    pages: {},
    sectionSearches: {},
  })
  let repaired = false
  const saved = vi.fn()
  const proposal = {
    case_id: "case",
    evidence_file_id: "file",
    filename: "Example no activity.pdf",
    currency: "MXN",
    revision: "a".repeat(64),
    page_numbers: [1, 2, 3],
    statement_page_numbers: [1, 2, 3],
    can_import_balances: true,
    transaction_count: 0,
    needs_attention: 0,
    issues: [],
    metadata: {
      holder: "Example company",
      account_number: "00001234567",
      institution: "Scotiabank Mexico",
      period: "2026-01-19 - 2026-01-30",
      period_start: "2026-01-19",
      period_end: "2026-01-30",
    },
    rows: ["Opening", "Closing"].map((role, index) => ({
      id: `1:0:${index}`,
      page_number: 1,
      table_index: 0,
      row_index: index,
      kind: "balance",
      excluded: true,
      issues: [],
      fields: {
        description: `${role} Balance`,
        balance: "0",
        balance_column: "1",
      },
      source_cells: [
        {
          column_index: 0,
          expected_text: `${role} balance`,
          locator: { kind: "page_only", page: 1 },
        },
        {
          column_index: 1,
          expected_text: "$0.00",
          locator: { kind: "page_only", page: 1 },
        },
      ],
    })),
  }
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (url.includes("/incomplete-records?"))
      return {
        records: [],
        total: repaired ? 0 : 162,
        statements: [
          { evidence_file_id: "file", filename: proposal.filename, count: 162 },
        ],
      } as never
    if (url.includes("/refresh-reading?")) {
      expect(options?.body).toEqual({
        expected_revision: "b".repeat(64),
        expected_reading_revision: proposal.revision,
        currency: "MXN",
      })
      repaired = true
      return {
        case_id: "case",
        evidence_file_id: "file",
        source_document_id: "updated",
        account_id: "account",
        applied: true,
        transaction_count: 0,
        record_count: 0,
        incomplete_count: 0,
      } as never
    }
    return {
      ...proposal,
      current_import: {
        source_document_id: repaired ? "updated" : "previous",
        evidence_file_id: "file",
        revision: "b".repeat(64),
        transaction_count: 0,
        incomplete_count: repaired ? 0 : 162,
        refresh_available: !repaired,
        refresh_transaction_count: 0,
      },
    } as never
  })
  function Journey() {
    const [review, setReview] = useState(false)
    return (
      <main className="p-5 bg-background text-foreground">
        {review ? (
          <>
            <button onClick={() => setReview(false)}>
              Back to Transactions
            </button>
            <StatementImportPanel caseId="case" onImported={saved} />
          </>
        ) : (
          <>
            <h1>Transactions</h1>
            <ImportedRecordsPanel
              caseId="case"
              params={{}}
              onOpen={vi.fn()}
              onReviewFile={() => {
                useStatementWorkspace
                  .getState()
                  .select("anonymous:case", "file")
                setReview(true)
              }}
            />
          </>
        )}
      </main>
    )
  }
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <Journey />
    </QueryClientProvider>
  )
  fireEvent.click(
    await screen.findByRole("button", {
      name: "Review statement: Example no activity.pdf",
    })
  )
  const save = await screen.findByRole("button", {
    name: "Save statement balances and open account",
  })
  expect(
    screen.getByText(/printed balances in MXN and no payments/)
  ).toBeVisible()
  expect(
    screen.queryByText(/transaction table could not be reconstructed/)
  ).not.toBeInTheDocument()
  save.scrollIntoView({ block: "center", behavior: "instant" })
  await page.screenshot({ path: "/tmp/loupe-zero-activity-recovery.png" })
  fireEvent.click(save)
  await waitFor(() =>
    expect(saved).toHaveBeenCalledWith(
      expect.objectContaining({
        transaction_count: 0,
        incomplete_count: 0,
        account_id: "account",
      })
    )
  )
  fireEvent.click(screen.getByRole("button", { name: "Back to Transactions" }))
  await waitFor(() =>
    expect(
      screen.queryByRole("region", {
        name: "Imported records with missing values",
      })
    ).not.toBeInTheDocument()
  )
})

it("explains the operation balance basis and retained prior-period settlements beside balance controls", async () => {
  await page.viewport(1280, 900)
  sessionStorage.clear()
  useAuthStore.setState({ user: null })
  useStatementWorkspace.setState({
    selections: {},
    reviewChoices: {},
    pages: {},
    sectionSearches: {},
  })
  useStatementWorkspace.getState().select("anonymous:case", "file")
  vi.mocked(fetchAPI).mockResolvedValue({
    case_id: "case",
    evidence_file_id: "file",
    filename: "Example operation balances.pdf",
    currency: "MXN",
    revision: "a".repeat(64),
    page_numbers: [1, 2],
    statement_page_numbers: [1, 2],
    balance_basis: "operation",
    prior_period_settlement_pages: [2],
    transaction_count: 1,
    needs_attention: 0,
    issues: [],
    metadata: {
      holder: "Example company",
      account_number: "00001234567",
      institution: "BBVA Mexico",
      balance_convention: "asset_balance",
      period: "January 2026",
      period_start: "2026-01-01",
      period_end: "2026-01-31",
    },
    rows: [
      ...["Opening", "Closing"].map((role, index) => ({
        id: `1:0:${index}`,
        page_number: 1,
        table_index: 0,
        row_index: index,
        kind: "balance",
        excluded: true,
        issues: [],
        fields: {
          description: `${role} Balance`,
          balance: index ? "4000" : "6000",
          balance_column: "1",
        },
        source_cells: [
          {
            column_index: 0,
            expected_text: `Saldo de Operación ${index ? "Final" : "Inicial"}`,
            locator: { kind: "page_only", page: 1 },
          },
          {
            column_index: 1,
            expected_text: index ? "40.00" : "60.00",
            locator: { kind: "page_only", page: 1 },
          },
        ],
      })),
      {
        id: "1:0:2",
        page_number: 1,
        table_index: 0,
        row_index: 2,
        kind: "transaction",
        excluded: false,
        issues: [],
        fields: {
          description: "Example payment",
          date: "2026-01-02",
          direction: "debit",
          amount_minor: "2000",
        },
        source_cells: [],
      },
    ],
  } as never)
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <main className="p-5 bg-background text-foreground">
        <StatementImportPanel caseId="case" onImported={vi.fn()} />
      </main>
    </QueryClientProvider>
  )
  const basis = await screen.findByRole("note", { name: "Balance basis" })
  expect(basis).toHaveTextContent(
    "Saldo de Operación Inicial and Saldo de Operación Final"
  )
  expect(basis).toHaveTextContent("PDF pages 2")
  expect(basis).toHaveTextContent(
    "excluded from this period’s imported payments and totals"
  )
  expect(
    screen.getByRole("button", { name: "Edit opening balance" })
  ).toHaveTextContent("60.00 MXN")
  basis.scrollIntoView({ block: "center", behavior: "instant" })
  await page.screenshot({ path: "/tmp/loupe-operation-balances.png" })
})

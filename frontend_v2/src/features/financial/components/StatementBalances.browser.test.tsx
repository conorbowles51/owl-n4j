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

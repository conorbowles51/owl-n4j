import "@/styles/globals.css"
import "../financial-workspace.css"
import { page } from "vitest/browser"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import { useFinancialDraftStore } from "../stores/financial-drafts"
import { useStatementWorkspace } from "../stores/statement-workspace"
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
type Request = {
  expected_revision: string
  rows: {
    id: string
    date: string
    reason: string
    amount_minor: string
    direction: string
    balance_minor: string | null
  }[]
}
let client: QueryClient
afterEach(() => {
  cleanup()
  client?.clear()
})
it.each([1280, 390])(
  "explains the exact source check, records it without changing values, and reopens saved current checks at %ipx",
  async (width) => {
    sessionStorage.clear()
    localStorage.clear()
    useAuthStore.setState({ user: null })
    useFinancialDraftStore.setState({ drafts: {} })
    useStatementWorkspace.setState({
      selections: {},
      pages: {},
      reviewChoices: {},
      sectionSearches: {},
    })
    useStatementWorkspace.getState().select("anonymous:case", "file")
    let saved:
      | {
          case_id: string
          evidence_file_id: string
          review_revision: string
          saved_at: string
          saved_by: { name: string }
          request: Request
        }
      | undefined
    const requests: Request[] = [],
      unexpected: string[] = []
    vi.mocked(fetchAPI).mockReset()
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
        return { ...source, saved_review: saved }
      if (url.includes("/coverage-check?"))
        return {
          case_id: "case",
          evidence_file_id: "file",
          available: true,
          revision: "c".repeat(64),
          candidates: [],
        }
      if (url.includes("/checks?")) {
        const row = (options?.body as Request).rows[0]
        const blockers = !row.date
          ? [
              {
                kind: "date",
                message: "Enter a valid transaction date.",
                target: {
                  kind: "transaction_field",
                  row_id: rowId,
                  field: "date",
                  page: 1,
                },
              },
            ]
          : !row.reason
            ? [
                {
                  kind: "reading",
                  message: warning,
                  target: {
                    kind: "transaction_field",
                    row_id: rowId,
                    field: "review",
                    page: 1,
                  },
                },
              ]
            : []
        return {
          revision,
          checks_revision: "b".repeat(64),
          applied: false,
          checks: [],
          admission: {
            revision: "b".repeat(64),
            can_import: !blockers.length,
            status: blockers.length ? "needs_review" : "reconciled",
            blockers,
          },
        }
      }
      if (url.includes("/progress?") && options?.method === "PUT") {
        const request = structuredClone(
          (options.body as { request: Request }).request
        )
        requests.push(request)
        saved = {
          case_id: "case",
          evidence_file_id: "file",
          review_revision: "d".repeat(64),
          saved_at: "2026-09-25T12:00:00Z",
          saved_by: { name: "Synthetic investigator" },
          request,
        }
        return saved
      }
      unexpected.push(`${options?.method || "GET"} ${url}`)
      throw Error(`Unexpected request ${url}`)
    })
    const mount = () => {
      client = new QueryClient({
        defaultOptions: {
          queries: { retry: false },
          mutations: { retry: false },
        },
      })
      render(
        <QueryClientProvider client={client}>
          <MemoryRouter>
            <main className="p-4">
              <StatementImportPanel caseId="case" onImported={() => {}} />
            </main>
          </MemoryRouter>
        </QueryClientProvider>
      )
    }
    const status = () =>
      screen.getByRole("region", { name: `Row review ${rowId}` })
    await page.viewport(width, 950)
    mount()
    await screen.findByRole("button", { name: "Review source reading" })
    expect(status()).toHaveTextContent(`Source reading: ${warning}`)
    expect(status()).not.toHaveTextContent("resolved in the current review")
    await page.screenshot({
      path: `/private/tmp/loupe-source-row-warning-${width}.png`,
      element: status().closest("[data-statement-row]")!,
    })
    await page
      .getByRole("button", { name: "Review source reading", exact: true })
      .click()
    await waitFor(() =>
      expect(
        screen.getByRole("region", { name: "Edit selected statement row" })
      ).toHaveFocus()
    )
    expect(
      screen.getByRole("textbox", { name: /^Corrected debit$/ })
    ).toHaveValue("12.34")
    expect(
      screen.getByRole("textbox", {
        name: /^Corrected printed balance$/,
      })
    ).toHaveValue("987.66")
    await page
      .getByRole("button", {
        name: "Mark checked against original",
        exact: true,
      })
      .click()
    await waitFor(() =>
      expect(status()).toHaveTextContent(
        "original extraction warning is resolved"
      )
    )
    expect(status()).toHaveTextContent("not yet saved")
    await page
      .getByRole("button", { name: "Save all review progress", exact: true })
      .click()
    await waitFor(() =>
      expect(status()).toHaveTextContent("Row review saved to the case.")
    )
    expect(requests[0].rows[0]).toMatchObject({
      date: "2026-04-15",
      direction: "debit",
      amount_minor: "1234",
      balance_minor: "98766",
      reason: "Checked against the original statement.",
    })
    await page
      .getByRole("button", { name: "Done editing this row", exact: true })
      .click()
    expect(within(status()).getByText(warning)).toBeVisible()
    await page.screenshot({
      path: `/private/tmp/loupe-source-row-review-${width}.png`,
      element: status().closest("[data-statement-row]")!,
    })
    cleanup()
    client.clear()
    sessionStorage.clear()
    useFinancialDraftStore.setState({ drafts: {} })
    mount()
    await waitFor(() =>
      expect(status()).toHaveTextContent("Row review saved to the case.")
    )
    await waitFor(() =>
      expect(status()).toHaveTextContent(
        "original extraction warning is resolved"
      )
    )
    await page
      .getByRole("button", { name: "View recorded check", exact: true })
      .click()
    await page
      .getByRole("textbox", { name: "Corrected transaction date", exact: true })
      .fill("")
    await screen.findByRole("button", { name: "Review transaction date" })
    expect(status()).toHaveTextContent(
      "Transaction date: Enter a valid transaction date."
    )
    expect(status()).not.toHaveTextContent("Row review saved to the case.")
    await page
      .getByRole("button", { name: "Review transaction date", exact: true })
      .click()
    await waitFor(() =>
      expect(screen.getByLabelText("Corrected transaction date")).toHaveFocus()
    )
    expect(
      screen.getByRole("button", {
        name: /^Import \d+ payments and view Transactions$/,
      })
    ).toBeDisabled()
    expect(unexpected).toEqual([])
  }
)

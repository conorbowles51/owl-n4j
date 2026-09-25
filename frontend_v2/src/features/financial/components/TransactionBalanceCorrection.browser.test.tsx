import "@/styles/globals.css"
import "../financial-workspace.css"
import { page } from "vitest/browser"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  act,
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
    <div className="h-36 border p-3">
      Synthetic original PDF remains unchanged.
    </div>
  ),
}))

const revision = "a".repeat(64),
  rowId = "1:0:1"
const proposal = {
  case_id: "case",
  evidence_file_id: "file",
  filename: "Synthetic balance correction.pdf",
  currency: "EUR",
  revision,
  metadata: {
    holder: "Example Company",
    account_number: "00123",
    institution: "Example Bank",
    period: "January 2026",
    period_start: "2026-01-01",
    period_end: "2026-01-31",
  },
  rows: [
    {
      id: rowId,
      kind: "transaction",
      excluded: false,
      page_number: 1,
      table_index: 0,
      row_index: 1,
      fields: {
        date: "2026-01-05",
        description: "Synthetic payment",
        amount_minor: "15781",
        direction: "debit",
        balance: '4726"',
        balance_column: "1",
      },
      source_cells: [
        {
          column_index: 0,
          expected_text: "Synthetic payment",
          locator: { kind: "page_only", page: 1 },
        },
        {
          column_index: 1,
          expected_text: '4726"',
          locator: { kind: "page_only", page: 1 },
        },
      ],
      issues: ["The extracted balance contains an unreadable character."],
    },
  ],
  issues: [],
  transaction_count: 1,
  needs_attention: 1,
  page_numbers: [1],
}
type Request = Record<string, unknown> & {
  rows: {
    id: string
    balance_minor: string | null
    description: string
    amount_minor: string
    excluded: boolean
  }[]
}
let client: QueryClient
afterEach(() => {
  cleanup()
  client?.clear()
})

it.each([1280, 390])(
  "keeps corrected balance, save outcome and unresolved checks distinct through close/reopen at %ipx",
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
    let resolveSave: () => void = () => {},
      rejectSave: () => void = () => {}
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
              original_filename: proposal.filename,
              status: "processed",
            },
          ],
        }
      if (url.includes("/statement-import/file?") && !options?.method)
        return { ...proposal, saved_review: saved }
      if (url.includes("/coverage-check?"))
        return {
          case_id: "case",
          evidence_file_id: "file",
          available: true,
          revision: "c".repeat(64),
          candidates: [],
        }
      if (url.includes("/checks?")) {
        const request = options?.body as Request
        const value = request.rows.find(
          (row) => row.id === rowId
        )!.balance_minor
        const ready = value === "84219"
        return {
          revision,
          checks_revision: "b".repeat(64),
          applied: false,
          checks: [],
          admission: {
            revision: "b".repeat(64),
            can_import: ready,
            status: ready ? "reconciled" : "needs_review",
            blockers: ready
              ? []
              : [
                  {
                    row_id: rowId,
                    message: "Payments do not add up to this printed balance.",
                    field: "balance",
                    target: {
                      kind: "transaction_field",
                      row_id: rowId,
                      field: "balance",
                      page: 1,
                    },
                  },
                ],
          },
        }
      }
      if (url.includes("/progress?") && options?.method === "PUT") {
        const request = structuredClone(
          (options.body as { request: Request }).request
        )
        requests.push(request)
        return new Promise((resolve, reject) => {
          resolveSave = () => {
            saved = {
              case_id: "case",
              evidence_file_id: "file",
              review_revision: "d".repeat(64),
              saved_at: "2026-09-25T12:00:00Z",
              saved_by: { name: "Synthetic investigator" },
              request,
            }
            resolve(saved)
          }
          rejectSave = () => reject(Error("Synthetic connection interrupted."))
        })
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
    const note = () =>
      screen.getByRole("note", { name: `Balance correction ${rowId}` })
    const fillBalance = (value: string) =>
      page
        .getByRole("textbox", {
          name: "Corrected printed balance",
          exact: true,
        })
        .fill(value)
    const save = () =>
      page
        .getByRole("button", { name: "Save all review progress", exact: true })
        .click()
    await page.viewport(width, 950)
    mount()
    await screen.findByRole("button", { name: "Edit this row" })
    await page
      .getByRole("button", { name: "Edit this row", exact: true })
      .click()
    await fillBalance("500.25")
    await waitFor(() =>
      expect(note()).toHaveTextContent(
        "Still needs review: Payments do not add up"
      )
    )
    expect(note()).toHaveTextContent("Reviewed balance: 500.25 EUR")
    expect(note()).toHaveTextContent(
      "Row changes are not yet saved to the case."
    )
    await save()
    await waitFor(() => expect(requests).toHaveLength(1))
    expect(
      screen.getByRole("button", { name: "Saving all review progress…" })
    ).toBeDisabled()
    expect(
      screen.getByRole("textbox", { name: "Corrected printed balance" })
    ).toBeDisabled()
    await act(async () => resolveSave())
    expect(note()).toHaveTextContent("Row correction saved to the case.")
    await fillBalance("510.25")
    expect(note()).toHaveTextContent(
      "Row changes are not yet saved to the case."
    )
    expect(requests[0].rows[0].balance_minor).toBe("50025")
    await save()
    await waitFor(() => expect(requests).toHaveLength(2))
    await act(async () => rejectSave())
    await waitFor(() => expect(note()).toHaveTextContent("Save not confirmed."))
    expect(
      screen.getByRole("textbox", { name: "Corrected printed balance" })
    ).toHaveValue("510.25")
    await save()
    await waitFor(() => expect(requests).toHaveLength(3))
    await act(async () => resolveSave())
    await waitFor(() =>
      expect(note()).toHaveTextContent("Row correction saved to the case.")
    )
    await waitFor(() =>
      expect(note()).toHaveTextContent(
        "Still needs review: Payments do not add up"
      )
    )
    expect(
      screen.getByRole("button", {
        name: "Import 1 payments and view Transactions",
      })
    ).toBeDisabled()
    await page
      .getByRole("button", { name: "Done editing this row", exact: true })
      .click()
    expect(
      screen.queryByRole("region", { name: "Edit selected statement row" })
    ).toBeNull()
    expect(note()).toBeVisible()
    expect(note()).toHaveTextContent('Original reading: 4726"')
    expect(screen.getByRole("button", { name: '4726"' })).toBeVisible()
    await page.screenshot({
      path: `/private/tmp/loupe-reviewed-balance-${width}.png`,
      element: note().closest("section")!,
    })
    cleanup()
    client.clear()
    sessionStorage.clear()
    useFinancialDraftStore.setState({ drafts: {} })
    mount()
    await screen.findByRole("button", { name: "View correction" })
    expect(note()).toHaveTextContent("Row correction saved to the case.")
    expect(note()).toHaveTextContent("Reviewed balance: 510.25 EUR")
    await waitFor(() =>
      expect(note()).toHaveTextContent(
        "Still needs review: Payments do not add up"
      )
    )
    await page
      .getByRole("button", { name: "View correction", exact: true })
      .click()
    expect(
      screen.getByRole("textbox", { name: "Corrected printed balance" })
    ).toHaveValue("510.25")
    await page
      .getByRole("textbox", { name: "Corrected description", exact: true })
      .fill("Later payment description")
    expect(note()).toHaveTextContent(
      "Row changes are not yet saved to the case."
    )
    await fillBalance("842.19")
    await waitFor(() =>
      expect(note()).toHaveTextContent("Current statement checks allow import.")
    )
    expect(note()).toHaveTextContent(
      "Row changes are not yet saved to the case."
    )
    await save()
    await waitFor(() => expect(requests).toHaveLength(4))
    await act(async () => resolveSave())
    await waitFor(() =>
      expect(note()).toHaveTextContent("Row correction saved to the case.")
    )
    expect(requests[3].rows[0]).toMatchObject({
      balance_minor: "84219",
      description: "Later payment description",
      amount_minor: "15781",
      excluded: false,
    })
    expect(
      within(note()).getByText(/Retained for comparison/)
    ).toHaveTextContent('4726"')
    await fillBalance("not readable")
    expect(note()).toHaveTextContent(
      "Not a valid amount (entered: not readable)"
    )
    await save()
    await waitFor(() => expect(requests).toHaveLength(5))
    await act(async () => resolveSave())
    await waitFor(() =>
      expect(note()).toHaveTextContent("Row changes are not yet saved")
    )
    expect(requests[4].rows[0].balance_minor).toBe("")
    expect(note()).not.toHaveTextContent("Row correction saved to the case.")
    expect(unexpected).toEqual([])
  },
  20000
)

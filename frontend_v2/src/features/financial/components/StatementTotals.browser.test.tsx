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
  TransactionSourceHighlight: ({
    locatorPayload,
  }: {
    locatorPayload: unknown
  }) => (
    <div className="h-40 border p-3" aria-label="Synthetic original source">
      Synthetic source location: {JSON.stringify(locatorPayload)}
    </div>
  ),
}))

const revision = "a".repeat(64)
const totalIds = { credit: "3:0:5", debit: "3:0:6" }
const expected = { credit: "42700", debit: "19250" }
function row(
  id: string,
  kind: string,
  fields: Record<string, string>,
  excluded = true
) {
  const [pageNumber, , index] = id.split(":").map(Number)
  const source = {
    column_index: 1,
    expected_text: fields.balance || fields.amount_minor || "",
    locator: { kind: "page_only", page: pageNumber, synthetic_control: id },
  }
  return {
    id,
    kind,
    page_number: pageNumber,
    table_index: 0,
    row_index: index,
    excluded,
    fields,
    issues: [],
    source_cells: [source],
    value_sources: {
      balance: {
        page_number: pageNumber,
        table_index: 0,
        row_index: index,
        source_cell: source,
      },
    },
  }
}
const proposal = {
  case_id: "case",
  evidence_file_id: "file",
  filename: "Synthetic totals.pdf",
  currency: "EUR",
  revision,
  metadata: {
    holder: "Example Company",
    account_number: "00123",
    institution: "Example Bank",
    period: "January 2026",
    period_start: "2026-01-01",
    period_end: "2026-01-31",
    balance_convention: "asset_balance",
  },
  rows: [
    row("1:0:0", "balance", {
      description: "opening balance",
      balance: "100000",
    }),
    row(
      "1:0:1",
      "transaction",
      {
        date: "2026-01-05",
        description: "Synthetic incoming payment",
        amount_minor: expected.credit,
        direction: "credit",
      },
      false
    ),
    row(
      "1:0:2",
      "transaction",
      {
        date: "2026-01-10",
        description: "Synthetic outgoing payment",
        amount_minor: expected.debit,
        direction: "debit",
      },
      false
    ),
    // Totals are excluded controls on another page, after many ordinary rows.
    ...Array.from({ length: 56 }, (_, index) =>
      row(`2:0:${index}`, "narrative", {
        description: `Synthetic retained source line ${index + 1}`,
      })
    ),
    row(totalIds.credit, "statement_total", {
      description: "Total credits",
      total_direction: "credit",
      balance: "0",
    }),
    row(totalIds.debit, "statement_total", {
      description: "Total debits",
      total_direction: "debit",
      balance: "0",
    }),
    row("3:0:7", "balance", {
      description: "closing balance",
      balance: "123450",
    }),
  ],
  issues: [],
  transaction_count: 2,
  needs_attention: 0,
  page_numbers: [1, 2, 3],
}
type DraftRow = Record<string, unknown> & {
  id: string
  balance_minor: string | null
  excluded: boolean
  amount_minor: string
}
type Request = Record<string, unknown> & { rows: DraftRow[] }
let client: QueryClient
afterEach(() => {
  cleanup()
  client?.clear()
})

it.each([1280, 390])(
  "reviews both excluded totals against their sources and saves/reopens the exact corrections at %ipx",
  async (width) => {
    localStorage.clear()
    sessionStorage.clear()
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
    const checks: Request[] = [],
      saves: Request[] = [],
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
      if (url.includes("/checks?")) {
        const request = options?.body as Request
        checks.push(structuredClone(request))
        const comparisons = (["credit", "debit"] as const).map((direction) => {
          const value = request.rows.find(
            (item) => item.id === totalIds[direction]
          )?.balance_minor
          return {
            kind: `${direction}_total`,
            row_id: totalIds[direction],
            status: value === expected[direction] ? "matches" : "difference",
            expected_minor: expected[direction],
            printed_minor: value || "0",
            difference_minor: (
              BigInt(expected[direction]) - BigInt(value || "0")
            ).toString(),
          }
        })
        const blockers = comparisons
          .filter((check) => check.status !== "matches")
          .map((check) => ({
            message: `The ${check.kind === "credit_total" ? "credits" : "debits"} do not agree with the printed total.`,
            row_id: check.row_id,
            kind: "arithmetic",
            field: "balance",
            target: {
              kind: "balance",
              row_id: check.row_id,
              field: "balance",
              page: 3,
            },
          }))
        return {
          revision,
          checks_revision: "b".repeat(64),
          applied: false,
          checks: [
            {
              kind: "closing_balance",
              status: "matches",
              row_id: "3:0:7",
              expected_minor: "123450",
              printed_minor: "123450",
              difference_minor: "0",
            },
            ...comparisons,
          ],
          admission: {
            revision: "b".repeat(64),
            can_import: blockers.length === 0,
            status: blockers.length ? "needs_review" : "reconciled",
            blockers,
            calculation: {
              available: true,
              currency: "EUR",
              balance_convention: "asset_balance",
              opening_minor: "100000",
              credit_minor: expected.credit,
              debit_minor: expected.debit,
              calculated_closing_minor: "123450",
              printed_closing_minor: "123450",
              difference_minor: "0",
            },
          },
        }
      }
      if (url.includes("/coverage-check?"))
        return {
          case_id: "case",
          evidence_file_id: "file",
          available: true,
          revision: "c".repeat(64),
          candidates: [],
        }
      if (url.includes("/progress?") && options?.method === "PUT") {
        const request = (options.body as { request: Request }).request
        saves.push(structuredClone(request))
        saved = {
          case_id: "case",
          evidence_file_id: "file",
          review_revision: "d".repeat(64),
          saved_at: "2026-09-25T12:00:00Z",
          saved_by: { name: "Synthetic investigator" },
          request: structuredClone(request),
        }
        return saved
      }
      if (url.includes("/statement-import/file?") && !options?.method)
        return { ...proposal, saved_review: saved }
      unexpected.push(`${options?.method || "GET"} ${url}`)
      throw Error(`Unexpected request: ${url}`)
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
    await page.viewport(width, 950)
    mount()
    await screen.findByText("Printed credit total: needs checking")
    expect(
      screen.getByRole("button", {
        name: "Import 2 payments and view Transactions",
      })
    ).toBeDisabled()
    await page
      .getByRole("button", {
        name: "Show corrections and import choices",
        exact: true,
      })
      .click()
    expect(
      screen.getByRole("checkbox", { name: "Show excluded rows" })
    ).not.toBeChecked()
    expect(
      screen.queryByLabelText(`Printed credit total ${totalIds.credit}`)
    ).not.toBeInTheDocument()

    // Admission blocker and arithmetic check use the same source-bound editor.
    const blocker = screen.getByText(
      "The credits do not agree with the printed total."
    ).parentElement!
    await page
      .elementLocator(
        within(blocker).getByRole("button", {
          name: "Review printed credit total",
        })
      )
      .click()
    const credit = await screen.findByRole("textbox", {
      name: "Corrected printed credit total",
    })
    await waitFor(() => expect(credit).toHaveFocus())
    expect(
      screen.getByLabelText("Synthetic original source")
    ).toHaveTextContent('"synthetic_control":"3:0:5"')
    expect(
      screen.getByText(
        /PDF page 3, extracted row 6. Original reading: 0.00 EUR/
      )
    ).toBeVisible()
    expect(screen.queryByText(/Page 0 of/)).not.toBeInTheDocument()
    await page
      .getByRole("textbox", {
        name: "Corrected printed credit total",
        exact: true,
      })
      .fill("4x")
    const issues = screen.getByRole("region", {
      name: "Statement issues and edits",
    })
    expect(
      within(issues).getByText(
        /Enter a valid printed credit total from the source/
      )
    ).toBeVisible()
    await page
      .getByRole("button", { name: "Done editing this row", exact: true })
      .click()
    await page
      .elementLocator(
        within(issues).getByRole("button", { name: "Review row" })
      )
      .click()
    await waitFor(() =>
      expect(
        screen.getByRole("textbox", { name: "Corrected printed credit total" })
      ).toHaveFocus()
    )
    expect(
      screen.getByRole("textbox", { name: "Corrected printed credit total" })
    ).toHaveValue("4x")
    await page
      .getByRole("textbox", {
        name: "Corrected printed credit total",
        exact: true,
      })
      .fill("427.00")
    await screen.findByText("Printed credit total: matches")
    expect(
      screen.getByRole("button", {
        name: "Import 2 payments and view Transactions",
      })
    ).toBeDisabled()
    expect(screen.getByText(/Original reading: 0.00 EUR/)).toBeVisible()
    await page
      .getByRole("button", { name: "Done editing this row", exact: true })
      .click()

    const arithmetic = screen.getByText(
      "Printed debit total: needs checking"
    ).parentElement!
    await page
      .elementLocator(
        within(arithmetic).getByRole("button", {
          name: "Review printed debit total",
        })
      )
      .click()
    const debit = await screen.findByRole("textbox", {
      name: "Corrected printed debit total",
    })
    await waitFor(() => expect(debit).toHaveFocus())
    expect(
      screen.getByLabelText("Synthetic original source")
    ).toHaveTextContent('"synthetic_control":"3:0:6"')
    await page
      .getByRole("textbox", {
        name: "Corrected printed debit total",
        exact: true,
      })
      .fill("192.50")
    await screen.findByText("Printed debit total: matches")
    await waitFor(() =>
      expect(
        screen.getByRole("button", {
          name: "Import 2 payments and view Transactions",
        })
      ).toBeEnabled()
    )
    expect(
      screen.getByRole("checkbox", { name: "Show excluded rows" })
    ).not.toBeChecked()
    await page.screenshot({
      path: `/private/tmp/loupe-printed-total-editor-${width}.png`,
      element: screen.getByRole("region", {
        name: "Edit selected statement row",
      }),
    })
    const latest = checks.at(-1)!
    for (const direction of ["credit", "debit"] as const) {
      expect(
        latest.rows.find((item) => item.id === totalIds[direction])
      ).toMatchObject({
        balance_minor: expected[direction],
        excluded: true,
        amount_minor: "0",
      })
    }
    expect(
      latest.rows
        .filter((item) => !item.excluded)
        .map((item) => item.amount_minor)
    ).toEqual([expected.credit, expected.debit])
    await page
      .getByRole("button", { name: "Save progress", exact: true })
      .click()
    await screen.findByText(
      "Progress saved to the case. You can reopen this statement on another device."
    )
    expect(saves).toHaveLength(1)
    const normalized = (rows: DraftRow[]) =>
      rows.map((item) => ({
        ...item,
        manual_page: item.manual_page ?? null,
        source_order_anchor: item.source_order_anchor ?? null,
      }))
    expect(normalized(saves[0].rows)).toEqual(normalized(latest.rows))
    cleanup()
    client.clear()
    sessionStorage.clear()
    useFinancialDraftStore.setState({ drafts: {} })
    mount()
    await screen.findByText("Printed debit total: matches")
    expect(
      screen.getByRole("button", {
        name: "Import 2 payments and view Transactions",
      })
    ).toBeEnabled()
    await page
      .getByRole("button", { name: "Review printed credit total", exact: true })
      .click()
    expect(
      screen.getByRole("textbox", { name: "Corrected printed credit total" })
    ).toHaveValue("427.00")
    expect(screen.getByText(/Original reading: 0.00 EUR/)).toBeVisible()
    expect(unexpected).toEqual([])
  },
  20000
)

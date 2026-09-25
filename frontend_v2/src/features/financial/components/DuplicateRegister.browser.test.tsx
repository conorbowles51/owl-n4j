import "@/styles/globals.css"
import "../financial-workspace.css"
import { useState } from "react"
import {
  QueryClient,
  QueryClientProvider,
  useQueryClient,
} from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { page } from "vitest/browser"
import { fetchAPI } from "@/lib/api-client"
import { StatementFilesPanel } from "./StatementFilesPanel"
import { StatementDuplicateDecision } from "./StatementDuplicateDecision"
import type { StatementDuplicateDisposition } from "../lib/statement-duplicate"
import { useStatementWorkspace } from "../stores/statement-workspace"

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
vi.mock("./StatementRecoveryPanel", () => ({
  StatementRecoveryPanel: () => null,
}))
vi.mock("@/features/evidence/components/ResumableUploadsPanel", () => ({
  ResumableUploadsPanel: () => null,
}))
afterEach(() => {
  cleanup()
  vi.resetAllMocks()
})
const caseId = "10000000-0000-4000-8000-000000000001"
const fileId = "10000000-0000-4000-8000-000000000002"
const initial: StatementDuplicateDisposition = {
  policy: "pending-statement-duplicate-v1",
  reading_revision: "a".repeat(64),
  revision: "b".repeat(64),
  current: true,
  status: "ignored",
  label: "Duplicate - Ignored by system",
  reason: "The financial contents match the retained source.",
  matched_fields: ["bank", "full_account_number", "account_holder"],
  basis: "identical_financial_reading",
  retained: {
    evidence_file_id: "10000000-0000-4000-8000-000000000003",
    filename: "Retained synthetic statement.pdf",
    page_number: 1,
  },
}
let decision = initial
function Harness() {
  const [open, setOpen] = useState(false)
  const [current, setCurrent] = useState(decision)
  const client = useQueryClient()
  return (
    <main className="p-4">
      {open ? (
        <>
          <button onClick={() => setOpen(false)}>
            Back to statement files
          </button>
          <StatementDuplicateDecision
            caseId={caseId}
            fileId={fileId}
            readingRevision={initial.reading_revision}
            decision={current}
            canEdit
            currency="USD"
            onDecision={(updated) => {
              setCurrent(updated)
              void client.invalidateQueries({
                queryKey: ["statement-import-status", caseId],
              })
            }}
          />
        </>
      ) : (
        <StatementFilesPanel
          caseId={caseId}
          register
          onOpen={() => setOpen(true)}
        />
      )}
    </main>
  )
}
it("opens an ignored period from the register, restores comparison, then returns to updated counts", async () => {
  await page.viewport(1440, 1050)
  useStatementWorkspace.setState({ selections: {}, reviewChoices: {} })
  decision = initial
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (options?.method === "POST") {
      expect(url).toContain("duplicate-disposition")
      expect(options.body).toMatchObject({
        action: "restore",
        expected_decision_revision: initial.revision,
      })
      decision = {
        ...initial,
        revision: "c".repeat(64),
        status: "restored",
        label: "Restored for review",
        reason: "Compare both source statements.",
      }
      return {
        case_id: caseId,
        evidence_file_id: fileId,
        statement_id: null,
        duplicate_disposition: decision,
      }
    }
    if (url.includes("/statement-import/files"))
      return {
        case_id: caseId,
        truncated: false,
        files: [
          {
            evidence_file_id: fileId,
            current_transactions: 0,
            periods: [],
            prepared_periods: 2,
            ignored_periods: decision.status === "ignored" ? 1 : 0,
            available_periods: 1,
            periods_with_checks: decision.status === "ignored" ? 0 : 1,
            duplicate_dispositions: [
              { statement_id: null, currency: "USD", decision },
            ],
            ready_periods: [
              {
                statement_id: "d".repeat(64),
                holder: "Synthetic company",
                institution: "Synthetic bank",
                account: "TEST-2",
                currency: "USD",
                period_start: "2026-02-01",
                period_end: "2026-02-28",
                transaction_count: 3,
                incomplete_count: 0,
                problem_count: 0,
              },
            ],
          },
        ],
      }
    return {
      files: [
        {
          id: fileId,
          case_id: caseId,
          original_filename: "Synthetic mixed-period file.pdf",
          status: "processed",
        },
      ],
    }
  })
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter>
        <Harness />
      </MemoryRouter>
    </QueryClientProvider>
  )
  fireEvent.change(await screen.findByLabelText("Show files"), {
    target: { value: "duplicates" },
  })
  expect(screen.getByText(/1 duplicate period ignored/)).toBeVisible()
  fireEvent.click(screen.getByText("Duplicate decisions · evidence retained"))
  expect(
    screen.getByText("Retained source: Retained synthetic statement.pdf")
  ).toBeVisible()
  fireEvent.click(
    screen.getByRole("button", { name: "Review duplicate decision" })
  )
  expect(
    screen.getByRole("heading", { name: "Duplicate - Ignored by system" })
  ).toBeVisible()
  fireEvent.click(
    screen.getByRole("button", { name: "Restore for comparison" })
  )
  expect(
    await screen.findByRole("heading", { name: "Restored for review" })
  ).toBeVisible()
  fireEvent.click(
    screen.getByRole("button", { name: "Back to statement files" })
  )
  await screen.findByRole("button", {
    name: "Show 1 files with checks to review",
  })
  expect(
    screen.getByRole("button", {
      name: "Show 1 statement period ready to import",
    })
  ).toBeVisible()
  expect(
    screen.queryByText(/1 duplicate period ignored/)
  ).not.toBeInTheDocument()
  expect(
    vi.mocked(fetchAPI).mock.calls.filter(([, opts]) => opts?.method === "POST")
  ).toHaveLength(1)
  await page.viewport(420, 1000)
  await waitFor(() =>
    expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(422)
  )
})

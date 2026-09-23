import "@/styles/globals.css"
import "../financial-workspace.css"
import { page } from "vitest/browser"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import { beforeEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { StatementFilesPanel } from "./StatementFilesPanel"
import { FinancialBatchPanel } from "./FinancialBatchPanel"
import { useFinancialDraftStore } from "../stores/financial-drafts"
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
vi.mock("@/features/evidence/components/ResumableUploadsPanel", () => ({
  ResumableUploadsPanel: () => null,
}))

const files = [0, 1].map((i) => ({
  id: `file-${i}`,
  case_id: "case",
  original_filename: `Example ${i}.pdf`,
  status: "processed",
}))
const items = files.map((file, i) => ({
  key: `period-${i}`,
  file_id: file.id,
  filename: file.original_filename,
  source_id: i ? null : "source",
  statement_id: null,
  revision: "a".repeat(64),
  status: i ? "Not imported" : "Imported",
  values: {
    holder: "",
    account_number: `000${i}`,
    institution: "Example Bank",
    currency: "MXN",
    period_start: "2026-01-01",
    period_end: "2026-01-31",
  },
}))
let saved = false
let saveBody:
  | { changes: Record<string, string>; targets: { file_id: string }[] }
  | undefined
beforeEach(() => {
  vi.resetAllMocks()
  useFinancialDraftStore.setState({ drafts: {} })
  saved = false
  saveBody = undefined
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (url.includes("/account-details/statements"))
      return {
        case_id: "case",
        notices: [],
        items: items.map((item) => ({
          ...item,
          values: { ...item.values, holder: saved ? "Example Holdings" : "" },
        })),
      } as never
    if (url.includes("/account-details/preview")) {
      const body = options?.body as {
        changes: Record<string, string>
        targets: { file_id: string }[]
      }
      return {
        case_id: "case",
        preview_revision: "b".repeat(64),
        updated: body.targets.length,
        items: items
          .filter((item) =>
            body.targets.some((t) => t.file_id === item.file_id)
          )
          .map((item) => ({
            ...item,
            after: { ...item.values, ...body.changes },
            changes: { holder: { before: "", after: body.changes.holder } },
          })),
      } as never
    }
    if (url.includes("/account-details/save")) {
      saved = true
      saveBody = options?.body as typeof saveBody
      return {
        case_id: "case",
        updated: 2,
        imported: 1,
        drafts: 1,
        unchanged: 0,
        items: [],
        account_changes: [],
      } as never
    }
    if (url.includes("/statement-import/files"))
      return { case_id: "case", files: [], truncated: false } as never
    if (url.includes("/batches/batch"))
      return {
        id: "batch",
        case_id: "case",
        status: "review",
        files: files.map((file) => ({
          file_id: file.id,
          source_id: file.id,
          filename: file.original_filename,
          status: "checked",
        })),
        counts: {},
        ready_transactions: 0,
        ready_revision: "a".repeat(64),
        total: 0,
        items: [],
      } as never
    return { files } as never
  })
})
function mount(batch = false) {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter
        initialEntries={["/cases/case/financial?view=statements&batch=batch"]}
      >
        {batch ? (
          <FinancialBatchPanel caseId="case" />
        ) : (
          <StatementFilesPanel caseId="case" register />
        )}
      </MemoryRouter>
    </QueryClientProvider>
  )
}
it("selects PDFs from Statement files, reviews the exact account changes, saves and reopens", async () => {
  await page.viewport(1280, 900)
  mount()
  expect(
    await screen.findByRole("button", { name: "Edit account details" })
  ).toBeDisabled()
  fireEvent.click(
    await screen.findByRole("button", { name: "Select all 2 shown files" })
  )
  fireEvent.click(screen.getByRole("button", { name: "Edit account details" }))
  fireEvent.click(
    await screen.findByRole("button", {
      name: "Select all 2 matching statements",
    })
  )
  fireEvent.click(screen.getByLabelText("Change account holder"))
  fireEvent.change(screen.getByLabelText("New account holder"), {
    target: { value: "Example Holdings" },
  })
  await page.screenshot({ path: "/tmp/loupe-bulk-account-select.png" })
  fireEvent.click(
    screen.getByRole("button", { name: "Review changes for 2 statements" })
  )
  await screen.findByRole("button", { name: "Save changes to 2 statements" })
  const dialog = screen.getByRole("dialog")
  expect(within(dialog).getAllByText("Example Holdings")).toHaveLength(2)
  expect(saved).toBe(false)
  await page.screenshot({ path: "/tmp/loupe-bulk-account-preview.png" })
  fireEvent.click(
    screen.getByRole("button", { name: "Save changes to 2 statements" })
  )
  await waitFor(() =>
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  )
  expect(
    screen.getByText(/Account details saved for 2 statements/)
  ).toHaveTextContent("1 imported statements updated; 1 saved for later import")
  expect(saveBody?.changes).toEqual({ holder: "Example Holdings" })
  expect(saveBody?.targets).toHaveLength(2)
  fireEvent.click(screen.getByRole("button", { name: "Review saved details" }))
  await waitFor(() =>
    expect(screen.getAllByText(/Example Holdings · Example Bank/)).toHaveLength(
      2
    )
  )
})
it("offers the same bulk account action in the processing batch and keeps controls reachable on a narrow screen", async () => {
  await page.viewport(390, 844)
  mount(true)
  fireEvent.click(
    await screen.findByRole("button", { name: "Edit account details" })
  )
  fireEvent.click(
    await screen.findByRole("button", {
      name: "Select all 2 matching statements",
    })
  )
  fireEvent.click(screen.getByLabelText("Change account holder"))
  fireEvent.change(screen.getByLabelText("New account holder"), {
    target: { value: "Example Holdings" },
  })
  const footer = screen
    .getByRole("button", { name: "Review changes for 2 statements" })
    .getBoundingClientRect()
  expect(footer.top).toBeGreaterThanOrEqual(0)
  expect(footer.bottom).toBeLessThanOrEqual(844)
  const dialog = screen.getByRole("dialog").getBoundingClientRect()
  expect(dialog.left).toBeGreaterThanOrEqual(0)
  expect(dialog.right).toBeLessThanOrEqual(390)
  await page.screenshot({ path: "/tmp/loupe-bulk-account-mobile.png" })
  fireEvent.click(screen.getByRole("button", { name: "Close — keep draft" }))
  fireEvent.click(screen.getByRole("button", { name: "Edit account details" }))
  expect(screen.getByLabelText("New account holder")).toHaveValue(
    "Example Holdings"
  )
})

it("finds ready statements and outstanding checks from the file list without opening a batch", async () => {
  const original = vi.mocked(fetchAPI).getMockImplementation()!
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (url.startsWith("/api/financial/statement-import/files?"))
      return {
        case_id: "case",
        truncated: false,
        files: files.map((file, i) => ({
          evidence_file_id: file.id,
          current_transactions: 0,
          periods: [],
          prepared_periods: 1,
          available_periods: i === 0 ? 1 : 0,
          periods_with_checks: i === 1 ? 1 : 0,
        })),
      } as never
    return original(url, options)
  })
  await page.viewport(1280, 850)
  mount()
  await screen.findByText(/1 available to import/)
  fireEvent.change(screen.getByLabelText("Show files"), {
    target: { value: "ready" },
  })
  expect(screen.getByText("Example 0.pdf")).toBeVisible()
  expect(screen.queryByText("Example 1.pdf")).toBeNull()
  fireEvent.change(screen.getByLabelText("Show files"), {
    target: { value: "checks" },
  })
  expect(screen.getByText("Example 1.pdf")).toBeVisible()
  expect(screen.queryByText("Example 0.pdf")).toBeNull()
  expect(screen.getByText(/1 periods have checks to review/)).toBeVisible()
})

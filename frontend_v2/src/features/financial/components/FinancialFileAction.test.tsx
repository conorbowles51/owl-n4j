import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, expect, it, vi } from "vitest"
import { StatementFilesPanel } from "./StatementFilesPanel"
import { fetchAPI } from "@/lib/api-client"
import { useStatementWorkspace } from "../stores/statement-workspace"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
const access = vi.hoisted(() => ({
  canEdit: true,
  canUpload: true,
  ready: true,
  error: false,
}))
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => access,
}))
let file = {
  id: "file",
  case_id: "case",
  original_filename: "letter.pdf",
  status: "processed",
  financial_imports_removed: false,
  financial_removed: false,
  financial_visibility_revision: "initial",
}
function mount() {
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter>
        <StatementFilesPanel caseId="case" />
      </MemoryRouter>
    </QueryClientProvider>
  )
}
beforeEach(() => {
  access.canEdit = true
  useAuthStore.setState({ user: null })
  useStatementWorkspace.setState({ selections: {}, reviewChoices: {} })
  file = {
    ...file,
    financial_imports_removed: false,
    financial_removed: false,
    financial_visibility_revision: "initial",
  }
  vi.mocked(fetchAPI).mockReset()
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    const preview = {
      case_id: "case",
      revision: "a".repeat(64),
      file_count: 1,
      reading_count: 1,
      transaction_count: 17,
      incomplete_count: 0,
      statement_count: 1,
      batch_count: 1,
      archived_batch_count: 1,
      updated_batch_count: 0,
      can_remove: true,
      files: [{ id: "file", filename: "letter.pdf" }],
    }
    if (url.includes("/removals/preview")) return preview
    if (url.includes("/removals/confirm")) {
      file = {
        ...file,
        financial_removed: true,
        financial_imports_removed: true,
      }
      return { ...preview, removed: true, restart_file_ids: ["file"] }
    }
    if (url.includes("/visibility?")) {
      const body = options?.body as { removed: boolean }
      file = {
        ...file,
        financial_removed: body.removed,
        financial_visibility_revision: body.removed ? "removed" : "restored",
      }
      return { ...file, evidence_file_id: file.id } as never
    }
    if (url.includes("/statement-import/files"))
      return { case_id: "case", files: [], truncated: false } as never
    return { files: [file] } as never
  })
})
it("removes imported records only after a preview, retains the PDF and offers fresh processing", async () => {
  useStatementWorkspace.getState().select("anonymous:case", "file")
  mount()
  fireEvent.click(
    await screen.findByRole("button", {
      name: "Remove from Financial: letter.pdf",
    })
  )
  const dialog = screen.getByRole("dialog")
  await within(dialog).findByText(/17 transactions/)
  expect(dialog).toHaveTextContent(
    "Original PDFs, case notes, findings and cited import history are retained"
  )
  expect(
    vi.mocked(fetchAPI).mock.calls.some(([url]) => url.includes("/confirm"))
  ).toBe(false)
  fireEvent.click(
    within(dialog).getByRole("button", { name: "Remove imports" })
  )
  await waitFor(() => expect(file.financial_removed).toBe(true))
  await waitFor(() =>
    expect(
      useStatementWorkspace.getState().selections["anonymous:case"]?.fileId
    ).toBeNull()
  )
  fireEvent.click(screen.getByRole("button", { name: /Removed files/ }))
  expect(
    await screen.findByRole("button", { name: "Process PDF afresh" })
  ).toBeEnabled()
  expect(
    vi
      .mocked(fetchAPI)
      .mock.calls.find(([url]) => url.includes("/removals/confirm"))?.[1]?.body
  ).toEqual({
    batch_ids: [],
    file_ids: ["file"],
    expected_revision: "a".repeat(64),
  })
})
it("keeps the imports visible when the preview has become stale", async () => {
  const base = vi.mocked(fetchAPI).getMockImplementation()!
  vi.mocked(fetchAPI).mockImplementation((url, options) =>
    url.includes("/removals/confirm")
      ? Promise.reject(Error("These imports changed since the preview."))
      : base(url, options)
  )
  mount()
  fireEvent.click(
    await screen.findByRole("button", {
      name: "Remove from Financial: letter.pdf",
    })
  )
  const confirm = await screen.findByRole("button", {
    name: "Remove imports",
  })
  await waitFor(() => expect(confirm).toBeEnabled())
  fireEvent.click(confirm)
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "changed since the preview"
  )
  expect(file.financial_removed).toBe(false)
})
it("shows persisted removed files to a viewer without offering restore", async () => {
  file.financial_removed = true
  access.canEdit = false
  mount()
  fireEvent.click(await screen.findByRole("button", { name: /Removed files/ }))
  expect(await screen.findByText("letter.pdf")).toBeVisible()
  expect(
    screen.queryByRole("button", { name: /Restore to Financial/ })
  ).not.toBeInTheDocument()
})

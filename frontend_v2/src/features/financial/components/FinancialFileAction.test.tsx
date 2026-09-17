import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
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
      <StatementFilesPanel caseId="case" />
    </QueryClientProvider>
  )
}
beforeEach(() => {
  access.canEdit = true
  useAuthStore.setState({ user: null })
  useStatementWorkspace.setState({ selections: {}, reviewChoices: {} })
  file = {
    ...file,
    financial_removed: false,
    financial_visibility_revision: "initial",
  }
  vi.mocked(fetchAPI).mockReset()
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
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
it("removes a file for the case, clears its open review, and restores it from Removed files", async () => {
  useStatementWorkspace.getState().select("anonymous:case", "file")
  mount()
  fireEvent.click(
    await screen.findByRole("button", {
      name: "Remove from Financial: letter.pdf",
    })
  )
  const dialog = screen.getByRole("dialog")
  expect(dialog).toHaveTextContent("The original stays in Evidence")
  fireEvent.click(
    within(dialog).getByRole("button", { name: "Remove from Financial" })
  )
  await waitFor(() =>
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  )
  expect(
    useStatementWorkspace.getState().selections["anonymous:case"]?.fileId
  ).toBeNull()
  fireEvent.click(screen.getByRole("button", { name: /Removed files/ }))
  fireEvent.click(
    await screen.findByRole("button", {
      name: "Restore to Financial: letter.pdf",
    })
  )
  await waitFor(() => expect(file.financial_removed).toBe(false))
  fireEvent.click(
    screen.getByRole("button", { name: "Back to financial files" })
  )
  expect(
    await screen.findByRole("button", {
      name: "Remove from Financial: letter.pdf",
    })
  ).toBeEnabled()
  const writes = vi
    .mocked(fetchAPI)
    .mock.calls.filter(([url]) => url.includes("/visibility?"))
  expect(writes.map(([, options]) => options?.body)).toEqual([
    { removed: true, expected_revision: "initial" },
    { removed: false, expected_revision: "removed" },
  ])
})
it("keeps the file visible when removal is rejected because it has imported records", async () => {
  const base = vi.mocked(fetchAPI).getMockImplementation()!
  vi.mocked(fetchAPI).mockImplementation((url, options) =>
    url.includes("/visibility?")
      ? Promise.reject(
          Error("This file already has imported financial records.")
        )
      : base(url, options)
  )
  mount()
  fireEvent.click(
    await screen.findByRole("button", {
      name: "Remove from Financial: letter.pdf",
    })
  )
  fireEvent.click(
    within(screen.getByRole("dialog")).getByRole("button", {
      name: "Remove from Financial",
    })
  )
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "already has imported financial records"
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

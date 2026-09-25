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
vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(),
}))
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
    original_filename: "letter.pdf",
    financial_imports_removed: false,
    financial_removed: false,
    financial_visibility_revision: "initial",
  }
  vi.mocked(fetchAPI).mockReset()
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (url.startsWith("/api/evidence-upload-")) return [] as never
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
it.each(["letter.pdf", "ledger.csv", "source.unusual"])(
  "hides and restores %s using only membership changes, retaining the saved review",
  async (filename) => {
    file.original_filename = filename
    useStatementWorkspace.getState().select("anonymous:case", "file")
    useStatementWorkspace
      .getState()
      .setReviewChoice("anonymous:case:file", {
        statementId: "saved-period",
        currency: "USD",
      })
    mount()
    fireEvent.click(
      await screen.findByRole("button", {
        name: `Remove from Financial: ${filename}`,
      })
    )
    const dialog = screen.getByRole("dialog")
    expect(dialog).toHaveTextContent(
      "Saved notes, corrections and batch reviews are kept"
    )
    expect(
      vi
        .mocked(fetchAPI)
        .mock.calls.some(([, options]) => options?.method === "POST")
    ).toBe(false)
    fireEvent.click(
      within(dialog).getByRole("button", { name: "Remove from Financial" })
    )
    await waitFor(() => expect(file.financial_removed).toBe(true))
    await waitFor(() =>
      expect(
        useStatementWorkspace.getState().selections["anonymous:case"]?.fileId
      ).toBeNull()
    )
    const notice = await screen.findByText(
      `${filename} removed from Financial. The original and saved reviews are retained.`
    )
    expect(notice.parentElement).toHaveFocus()
    fireEvent.click(screen.getByRole("button", { name: "View removed files" }))
    fireEvent.click(
      await screen.findByRole("button", {
        name: `Restore to Financial: ${filename}`,
      })
    )
    await screen.findByText(
      `${filename} restored to Financial with its saved reviews.`
    )
    fireEvent.click(
      screen.getByRole("button", { name: "View financial files" })
    )
    expect(
      await screen.findByRole("button", {
        name: `Remove from Financial: ${filename}`,
      })
    ).toBeEnabled()
    expect(file.financial_imports_removed).toBe(false)
    expect(
      useStatementWorkspace.getState().reviewChoices["anonymous:case:file"]
    ).toEqual({ statementId: "saved-period", currency: "USD" })
    const writes = vi
      .mocked(fetchAPI)
      .mock.calls.filter(([, options]) => options?.method === "POST")
    expect(writes.map(([url]) => url)).toEqual(
      Array(2).fill(
        "/api/financial/statement-import/file/visibility?case_id=case"
      )
    )
    expect(writes.map(([, options]) => options?.body)).toEqual([
      { removed: true, expected_revision: "initial" },
      { removed: false, expected_revision: "removed" },
    ])
  }
)
it.each([
  "Another user changed this file. Refresh files before changing it again.",
  "This file or one of its retained readings is still processing. No job was stopped.",
  "This file already has imported financial records. Use Remove imports only if you intend to withdraw those saved records.",
])(
  "keeps the file and review visible after the server guard: %s",
  async (reason) => {
    const base = vi.mocked(fetchAPI).getMockImplementation()!
    vi.mocked(fetchAPI).mockImplementation((url, options) =>
      url.includes("/visibility?")
        ? Promise.reject(Error(reason))
        : base(url, options)
    )
    mount()
    fireEvent.click(
      await screen.findByRole("button", {
        name: "Remove from Financial: letter.pdf",
      })
    )
    const confirm = await screen.findByRole("button", {
      name: "Remove from Financial",
    })
    await waitFor(() => expect(confirm).toBeEnabled())
    fireEvent.click(confirm)
    expect(await screen.findByRole("alert")).toHaveTextContent(reason)
    expect(file.financial_removed).toBe(false)
    fireEvent.click(screen.getByRole("button", { name: "Keep file" }))
    expect(
      screen.getByRole("button", { name: "Remove from Financial: letter.pdf" })
    ).toBeVisible()
  }
)
it("keeps explicit import removal separate: withdrawn imports require fresh processing", async () => {
  file.financial_removed = true
  file.financial_imports_removed = true
  mount()
  fireEvent.click(await screen.findByRole("button", { name: /Removed files/ }))
  expect(
    await screen.findByRole("button", { name: "Process PDF afresh" })
  ).toBeEnabled()
  expect(
    screen.queryByRole("button", { name: /Restore to Financial/ })
  ).not.toBeInTheDocument()
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

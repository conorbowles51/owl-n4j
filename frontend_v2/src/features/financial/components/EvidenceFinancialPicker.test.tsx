import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, expect, it, vi } from "vitest"
import { EvidenceFinancialPicker } from "./EvidenceFinancialPicker"
import { fetchAPI } from "@/lib/api-client"
import { foldersAPI } from "@/features/evidence/folders.api"
import { MemoryRouter, useLocation } from "react-router-dom"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
vi.mock("@/features/evidence/folders.api", () => ({
  foldersAPI: { getContents: vi.fn() },
}))
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({ canEdit: true, canUpload: true }),
}))
beforeEach(() => {
  vi.resetAllMocks()
  useAuthStore.setState({ user: null })
})
it("browses folders, retains overlapping selections and sends existing PDFs without uploading copies", async () => {
  vi.mocked(foldersAPI.getContents).mockImplementation(
    async (_case, folder) =>
      ({
        breadcrumbs: folder ? [{ id: "folder", name: "Bank records" }] : [],
        folders: folder ? [] : [{ id: "folder", name: "Bank records" }],
        files: folder
          ? [
              {
                id: "pdf",
                original_filename: "statement.pdf",
                status: "processed",
              },
              {
                id: "text",
                original_filename: "notes.txt",
                status: "processed",
              },
            ]
          : [],
        file_total: folder ? 2 : 0,
        file_limit: 100,
        file_offset: 0,
      }) as never
  )
  vi.mocked(fetchAPI).mockImplementation(async (url) =>
    url.includes("/selection/resolve")
      ? ({
          case_id: "case",
          skipped_non_pdf: 1,
          files: [
            {
              id: "pdf",
              original_filename: "statement.pdf",
              status: "processed",
              financial_removed: false,
              financial_visibility_revision: "initial",
            },
          ],
        } as never)
      : ({
          case_id: "case",
          id: "batch",
        } as never)
  )
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter>
        <EvidenceFinancialPicker caseId="case" />
        <Location />
      </MemoryRouter>
    </QueryClientProvider>
  )
  fireEvent.click(screen.getByRole("button", { name: "Choose from Evidence" }))
  fireEvent.click(await screen.findByLabelText("Select folder Bank records"))
  fireEvent.click(screen.getByRole("button", { name: "Bank records" }))
  fireEvent.click(await screen.findByLabelText(/statement.pdf/))
  expect(screen.getByLabelText(/notes.txt/)).toBeEnabled()
  fireEvent.click(screen.getByRole("button", { name: "Review selected files" }))
  await screen.findByRole("heading", { name: /1 file/ })
  expect(vi.mocked(fetchAPI).mock.calls[0][1]?.body).toEqual({
    file_ids: ["pdf"],
    folder_ids: ["folder"],
    include_other_formats: true,
  })
  fireEvent.click(screen.getByRole("button", { name: /Send .* to Financial/ }))
  await waitFor(() =>
    expect(screen.getByTestId("location")).toHaveTextContent(
      "/cases/case/financial?view=statements&batch=batch"
    )
  )
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  expect(vi.mocked(fetchAPI).mock.calls[1][1]?.body).toEqual({
    request_id: expect.any(String),
    file_ids: ["pdf"],
    folder_ids: [],
  })
  expect(vi.mocked(fetchAPI).mock.calls.map(([url]) => url)).toEqual([
    "/api/financial/statement-import/selection/resolve?case_id=case",
    "/api/financial/statement-import/batches?case_id=case",
  ])
})

function Location() {
  const location = useLocation()
  return (
    <div data-testid="location">
      {location.pathname}
      {location.search}
    </div>
  )
}

it("saves mixed financial sources and sends only PDFs to statement preparation", async () => {
  const files = [
    "statement.pdf",
    "payments.csv",
    "accounts.xlsx",
    "invoice.docx",
    "receipt.png",
    "old.xls",
  ].map((name, n) => ({
    id: String(n),
    original_filename: name,
    status: "unprocessed",
    financial_removed: false,
    financial_visibility_revision: "initial",
  }))
  vi.mocked(foldersAPI.getContents).mockResolvedValue({
    breadcrumbs: [],
    folders: [],
    files,
    file_total: files.length,
  } as never)
  vi.mocked(fetchAPI).mockImplementation(async (url) => {
    if (url.includes("/selection/resolve"))
      return { case_id: "case", skipped_non_pdf: 0, files } as never
    if (url.includes("/selection/include"))
      return {
        case_id: "case",
        file_ids: files.slice(1).map((file) => file.id),
      } as never
    return { case_id: "case", id: "batch" } as never
  })
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter>
        <EvidenceFinancialPicker
          caseId="case"
          initialFileIds={files.map((file) => file.id)}
        />
        <Location />
      </MemoryRouter>
    </QueryClientProvider>
  )
  fireEvent.click(screen.getByRole("button", { name: "Choose from Evidence" }))
  await screen.findByLabelText("Select file payments.csv")
  fireEvent.click(screen.getByRole("button", { name: "Review selected files" }))
  await screen.findByRole("heading", { name: "6 files to send to Financial" })
  fireEvent.click(
    screen.getByRole("button", { name: "Send 6 files to Financial" })
  )
  await waitFor(() =>
    expect(screen.getByTestId("location")).toHaveTextContent(
      "/cases/case/financial?view=statements&files=1"
    )
  )
  expect(vi.mocked(fetchAPI).mock.calls[1][1]?.body).toEqual({
    files: files
      .slice(1)
      .map((file) => ({
        evidence_file_id: file.id,
        expected_revision: "initial",
      })),
  })
  expect(vi.mocked(fetchAPI).mock.calls[2][1]?.body).toEqual({
    request_id: expect.any(String),
    file_ids: ["0"],
    folder_ids: [],
  })
})

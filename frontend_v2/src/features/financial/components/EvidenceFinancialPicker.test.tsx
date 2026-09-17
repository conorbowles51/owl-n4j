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
  expect(screen.getByLabelText(/notes.txt/)).toBeDisabled()
  fireEvent.click(screen.getByRole("button", { name: "Review selected PDFs" }))
  await screen.findByRole("heading", { name: /1 PDF/ })
  expect(vi.mocked(fetchAPI).mock.calls[0][1]?.body).toEqual({
    file_ids: ["pdf"],
    folder_ids: ["folder"],
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

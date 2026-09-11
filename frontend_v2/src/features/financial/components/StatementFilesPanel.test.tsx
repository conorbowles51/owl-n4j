import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, expect, it, vi } from "vitest"
import { StatementFilesPanel } from "./StatementFilesPanel"
import { fetchAPI } from "@/lib/api-client"
import { evidenceAPI } from "@/features/evidence/api"
vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
vi.mock("@/features/evidence/api", () => ({
  evidenceAPI: { preparePdfReview: vi.fn() },
}))
const file = {
  id: "file",
  case_id: "case",
  original_filename: "statement.pdf",
  status: "failed",
}
const status = { case_id: "case", files: [], truncated: false }
function responses(files = [file], saved = status) {
  vi.mocked(fetchAPI).mockImplementation(async (url) =>
    url.includes("/statement-import/files") ? saved : { files }
  )
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
  vi.resetAllMocks()
  responses()
})
it("reads the existing failed file without uploading another copy", async () => {
  vi.mocked(evidenceAPI.preparePdfReview).mockImplementation(async () => {
    responses([{ ...file, status: "processed" }])
    return { job_ids: ["job"] }
  })
  mount()
  fireEvent.click(
    await screen.findByRole("button", { name: "Retry reading: statement.pdf" })
  )
  await waitFor(() =>
    expect(evidenceAPI.preparePdfReview).toHaveBeenCalledWith("case", "file")
  )
  expect(
    await screen.findByRole("button", {
      name: /statement.pdf.*Ready to review/,
    })
  ).toBeEnabled()
  expect(
    vi
      .mocked(fetchAPI)
      .mock.calls.every(([url]) =>
        [
          "/api/evidence?case_id=case",
          "/api/financial/statement-import/files?case_id=case",
        ].includes(url)
      )
  ).toBe(true)
})
it("retains the file and reports an uncertain failed request without automatically retrying", async () => {
  vi.mocked(evidenceAPI.preparePdfReview).mockRejectedValue(
    Error("Connection lost.")
  )
  mount()
  fireEvent.click(
    await screen.findByRole("button", { name: "Retry reading: statement.pdf" })
  )
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Your uploaded PDF is retained"
  )
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Retry reading: statement.pdf" })
    ).toBeEnabled()
  )
  expect(evidenceAPI.preparePdfReview).toHaveBeenCalledTimes(1)
})
it("offers reading for an unprocessed file but never for an active job", async () => {
  responses([
    { ...file, status: "unprocessed" },
    {
      ...file,
      id: "active",
      original_filename: "active.pdf",
      status: "processing",
    },
  ])
  mount()
  expect(
    await screen.findByRole("button", { name: "Read statement: statement.pdf" })
  ).toBeEnabled()
  expect(
    screen.queryByRole("button", { name: /reading: active.pdf/i })
  ).not.toBeInTheDocument()
  expect(
    screen.getByRole("button", { name: /active.pdf.*processing/ })
  ).toBeDisabled()
})
it("shows saved import counts and periods after reopening the file list", async () => {
  vi.mocked(fetchAPI).mockImplementation(async (url) =>
    url.includes("/statement-import/files")
      ? {
          case_id: "case",
          truncated: false,
          files: [
            {
              evidence_file_id: "file",
              current_transactions: 12,
              periods: [
                {
                  id: "period",
                  account_id: "account",
                  account_label: "Business account",
                  start: "2023-01-01",
                  end: "2023-12-31",
                  source_status: "admitted",
                },
              ],
            },
          ],
        }
      : { files: [{ ...file, status: "processed" }] }
  )
  mount()
  expect(
    await screen.findByText("12 imported payments · 1 recorded periods")
  ).toBeInTheDocument()
  expect(
    screen.getByText(/Business account · 2023-01-01 to 2023-12-31/)
  ).toBeInTheDocument()
  expect(screen.queryByText("Ready to review")).not.toBeInTheDocument()
})

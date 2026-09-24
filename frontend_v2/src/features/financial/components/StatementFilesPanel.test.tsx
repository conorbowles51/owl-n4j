vi.mock("./StatementRecoveryPanel", () => ({
  StatementRecoveryPanel: () => null,
}))
// This existing workflow fixture has case editing and upload access.
vi.mock("../hooks/use-financial-access", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../hooks/use-financial-access")>()),
  useFinancialAccess: () => ({
    canEdit: true,
    canUpload: true,
    ready: true,
    error: false,
  }),
}))
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, expect, it, vi } from "vitest"
import { MemoryRouter, useLocation } from "react-router-dom"
import { StatementFilesPanel } from "./StatementFilesPanel"
import { fetchAPI } from "@/lib/api-client"
import { evidenceAPI } from "@/features/evidence/api"
vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
// Upload interruption is exercised with the real panel in Chromium.
vi.mock("@/features/evidence/components/ResumableUploadsPanel", () => ({
  ResumableUploadsPanel: () => null,
}))
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
function Location() {
  const location = useLocation()
  return (
    <output aria-label="Location">
      {location.pathname}
      {location.search}
    </output>
  )
}
function mount(register = false) {
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter>
        <StatementFilesPanel caseId="case" register={register} />
        <Location />
      </MemoryRouter>
    </QueryClientProvider>
  )
}
beforeEach(() => {
  vi.resetAllMocks()
  responses()
})
it("prepares all selected files directly, keeps hidden selections and reuses a failed request", async () => {
  const files = Array.from({ length: 3 }, (_, n) => ({
    ...file,
    id: `file-${n}`,
    original_filename: `Statements ${n}.pdf`,
    status: "processed",
  }))
  const attempts: unknown[] = []
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (options?.method === "POST") {
      attempts.push(options.body)
      if (attempts.length === 1) throw Error("Connection lost")
      return { id: "new-batch", case_id: "case" } as never
    }
    return (
      url.includes("/statement-import/files") ? status : { files }
    ) as never
  })
  mount(true)
  fireEvent.click(
    await screen.findByRole("button", { name: "Select all 3 shown files" })
  )
  fireEvent.change(screen.getByLabelText("Search statement files"), {
    target: { value: "Statements 1" },
  })
  expect(
    screen.getByText("3 files selected · 2 hidden by filters")
  ).toBeVisible()
  fireEvent.click(
    screen.getByRole("button", { name: "Prepare statements from 3 files" })
  )
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Your selection is kept"
  )
  expect(screen.getByLabelText("Select Statements 1.pdf")).toBeChecked()
  fireEvent.click(
    screen.getByRole("button", { name: "Prepare statements from 3 files" })
  )
  await waitFor(() =>
    expect(screen.getByLabelText("Location")).toHaveTextContent(
      "/cases/case/financial?view=statements&batch=new-batch"
    )
  )
  expect(attempts).toHaveLength(2)
  expect(attempts[0]).toEqual(attempts[1])
  expect(attempts[1]).toMatchObject({
    file_ids: ["file-0", "file-1", "file-2"],
    folder_ids: [],
  })
  expect(fetchAPI).not.toHaveBeenCalledWith(
    expect.stringContaining("/confirm"),
    expect.anything()
  )
})

it("does not navigate to a batch belonging to a different case", async () => {
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (options?.method === "POST")
      return { id: "wrong-batch", case_id: "other" } as never
    return (
      url.includes("/statement-import/files")
        ? status
        : { files: [{ ...file, status: "processed" }] }
    ) as never
  })
  mount(true)
  fireEvent.click(
    await screen.findByRole("button", { name: "Select all 1 shown file" })
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Prepare statements from 1 file" })
  )
  expect(await screen.findByRole("alert")).toHaveTextContent("another case")
  expect(screen.getByLabelText("Location")).not.toHaveTextContent("wrong-batch")
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
      name: /statement.pdf.*PDF read.*payments not yet imported/,
    })
  ).toBeEnabled()
  expect(
    vi
      .mocked(fetchAPI)
      .mock.calls.every(([url]) =>
        [
          "/api/evidence?case_id=case&include_reading_versions=true&financial_only=true",
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
    await screen.findByText("12 imported payments · 1 recorded period")
  ).toBeInTheDocument()
  expect(
    screen.getByText(/Business account · 2023-01-01 to 2023-12-31/)
  ).toBeInTheDocument()
  expect(screen.queryByText("Ready to review")).not.toBeInTheDocument()
})

it("shows a saved wire review as a finding and provides a link without suggesting a payment import", async () => {
  vi.mocked(fetchAPI).mockImplementation(async (url) =>
    url.includes("/statement-import/files")
      ? {
          case_id: "case",
          truncated: false,
          files: [
            {
              evidence_file_id: "file",
              current_transactions: 0,
              periods: [],
              wire_review_count: 1,
            },
          ],
        }
      : {
          files: [
            { ...file, original_filename: "wire.pdf", status: "processed" },
          ],
        }
  )
  mount()
  expect(
    await screen.findByRole("button", { name: /wire.pdf.*1 saved wire review/ })
  ).toBeEnabled()
  expect(
    screen.getByRole("link", { name: "Open saved wire reviews in Findings" })
  ).toHaveAttribute("href", "/cases/case/financial?view=findings")
  expect(screen.queryByText(/0 imported payments/)).toBeNull()
})

it("keeps a balance-only statement in the imported file filter", async () => {
  vi.mocked(fetchAPI).mockImplementation(async (url) =>
    url.includes("/statement-import/files")
      ? {
          case_id: "case",
          truncated: false,
          files: [
            {
              evidence_file_id: "file",
              current_transactions: 0,
              periods: [
                {
                  id: "period",
                  account_id: "account",
                  account_label: "BBVA example",
                  start: "2021-01-01",
                  end: "2021-01-31",
                  source_status: "admitted",
                },
              ],
            },
          ],
        }
      : { files: [{ ...file, status: "processed" }] }
  )
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <StatementFilesPanel caseId="case" register />
      </MemoryRouter>
    </QueryClientProvider>
  )
  expect(
    await screen.findByText("Statement saved · 1 recorded period · no payments")
  ).toBeVisible()
  fireEvent.change(screen.getByLabelText("Show files"), {
    target: { value: "imported" },
  })
  expect(
    screen.getByText("Statement saved · 1 recorded period · no payments")
  ).toBeVisible()
  fireEvent.change(screen.getByLabelText("Show files"), {
    target: { value: "review" },
  })
  expect(
    screen.queryByText("Statement saved · 1 recorded period · no payments")
  ).not.toBeInTheDocument()
})

it("shows non-PDF financial sources with their original and keeps them out of PDF bulk controls", async () => {
  responses([
    file,
    ...[
      "payments.csv",
      "invoice.docx",
      "accounts.xlsx",
      "receipt.png",
      "legacy.xls",
    ].map((name) => ({
      ...file,
      id: name,
      original_filename: name,
      status: "unprocessed",
    })),
  ])
  mount(true)
  const source = await screen.findByRole("article", {
    name: "Financial source payments.csv",
  })
  expect(source).toHaveTextContent(
    "Adding this source to Financial does not import transactions"
  )
  expect(
    screen.getByRole("article", { name: "Financial source legacy.xls" })
  ).toHaveTextContent("converted to XLSX or CSV")
  expect(
    screen.getAllByRole("link", { name: "Open source in Evidence" })[0]
  ).toHaveAttribute(
    "href",
    "/cases/case/evidence?file=payments.csv&from=financial"
  )
  expect(screen.queryByLabelText("Select payments.csv")).not.toBeInTheDocument()
  fireEvent.click(
    screen.getByRole("button", { name: "Select all 1 shown file" })
  )
  expect(
    screen.getByRole("button", { name: "Prepare statements from 1 file" })
  ).toBeEnabled()
  expect(screen.getByText("1 file selected")).toBeVisible()
  expect(evidenceAPI.preparePdfReview).not.toHaveBeenCalled()
})

import "@/styles/globals.css"
import { page } from "vitest/browser"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { TooltipProvider } from "@/components/ui/tooltip"
import { ApiError, fetchAPI } from "@/lib/api-client"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import { useFinancialDraftStore } from "../stores/financial-drafts"
import { useFinancialStore } from "../stores/financial.store"
import { useStatementWorkspace } from "../stores/statement-workspace"
import { FinancialPage } from "./FinancialPage"

vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()), fetchAPI: vi.fn(),
}))
vi.mock("@/features/cases/hooks/use-cases", () => ({
  useCase: () => ({ data: { id: "case", title: "Synthetic navigation case" }, isPending: false }),
}))
vi.mock("../hooks/use-financial-access", async (original) => ({
  ...(await original<typeof import("../hooks/use-financial-access")>()),
  useFinancialAccess: () => ({ canEdit: true, canUpload: true, ready: true, error: false }),
}))
vi.mock("../hooks/use-financial-data", () => {
  const idle = () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false })
  return {
    useTransactions: () => ({ data: { transactions: [] }, isLoading: false }),
    useFinancialCategories: () => ({ data: [] }),
    useFinancialEntities: () => ({ data: [] }),
    useCategorize: idle, useBatchCategorize: idle, useCreateCategory: idle,
    useUpdateDetails: idle, useUpdateAmount: idle, useSetFromTo: idle,
    useBatchSetFromTo: idle, useBulkCorrect: idle, useLinkSubTransaction: idle,
    useUnlinkSubTransaction: idle,
  }
})
vi.mock("../hooks/use-ledger-transactions", () => ({
  useLedgerTransactions: () => ({ data: { case_id: "case", transactions: [], total: 0 }, isPending: false, isError: false }),
}))
vi.mock("./TransactionSourceHighlight", () => ({
  TransactionSourceHighlight: ({ sourceDocumentId }: { sourceDocumentId: string }) => (
    <div className="h-64 rounded border p-4">Synthetic original: {sourceDocumentId}</div>
  ),
}))

const batch = {
  id: "batch-origin", case_id: "case", status: "review",
  files: [{
    source_id: "older-reading", file_id: "older-reading", review_file_id: "current-reading",
    filename: "Synthetic recovery.pdf", status: "error", error: "Check the retained reading.",
  }],
  counts: { attention: 1 }, ready_transactions: 0, ready_revision: "a".repeat(64), total: 0, items: [],
}
const file = { id: "current-reading", case_id: "case", original_filename: "Synthetic recovery.pdf", status: "processed" }
const otherFile = { ...file, id: "other-reading", original_filename: "Other synthetic statement.pdf" }
const proposal = {
  case_id: "case", evidence_file_id: file.id, filename: file.original_filename, currency: "USD", revision: "b".repeat(64),
  metadata: { holder: "Synthetic Company", account_number: "0001", institution: "Example Bank", period: "January 2026", period_start: "2026-01-01", period_end: "2026-01-31" },
  rows: [], issues: [], transaction_count: 0, needs_attention: 1, page_numbers: [1],
  reading_failure: "Synthetic reading retained for review; compare the original before retrying.",
}
function RouteControls() {
  const location = useLocation()
  const navigate = useNavigate()
  return <><output aria-label="Current route">{location.search}</output><button onClick={() => navigate(-1)}>Browser back</button></>
}
function mount(entry = "/cases/case/financial?view=statements") {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>
      <TooltipProvider>
        <MemoryRouter initialEntries={[entry]}>
          <Routes><Route path="/cases/:id/financial" element={<main className="flex h-[900px] flex-col"><FinancialPage /><RouteControls /></main>} /></Routes>
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>
  )
}
beforeEach(async () => {
  localStorage.clear()
  sessionStorage.clear()
  useAuthStore.setState({ user: null })
  useFinancialStore.getState().reset()
  useFinancialDraftStore.setState({ drafts: {} })
  useStatementWorkspace.setState({ selections: {}, reviewChoices: {}, pages: {}, sectionSearches: {} })
  vi.resetAllMocks()
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (options?.method) throw Error("This navigation journey must not write or reprocess data.")
    if (url.includes("/batches/list?")) return { case_id: "case", batches: [{ id: batch.id, status: "review", created_at: "2026-09-25T10:00:00Z", file_count: 1, failed_files: 1 }] } as never
    if (url.includes(`/batches/${batch.id}?`)) return batch as never
    if (url.startsWith("/api/evidence?")) return { files: [file, otherFile] } as never
    if (url.startsWith("/api/evidence-upload-")) return [] as never
    if (url.includes("/statement-import/files?")) return { case_id: "case", truncated: false, files: [] } as never
    if (url.includes("/deployment-recovery?")) return { run: null, total: 0, counts: {}, items: [] } as never
    if (url.includes(`/statement-import/${file.id}?`)) return proposal as never
    if (url.includes(`/statement-import/${otherFile.id}?`)) return { ...proposal, evidence_file_id: otherFile.id, filename: otherFile.original_filename } as never
    return { case_id: "case", accounts: [], transactions: [], total: 0, runs: [], decisions: [], categories: [], files: [], items: [], entries: [] } as never
  })
  await page.viewport(1360, 1000)
})
afterEach(cleanup)

it("retries the exact retained reading from its job card, shows progress and returns from its source to the same batch", async () => {
  let retryResolve: (value: unknown) => void = () => {}
  let retried = false,
    completed = false,
    jobReads = 0
  const posts: string[] = []
  const original = vi.mocked(fetchAPI).getMockImplementation()!
  const receipt = {
    queued: true,
    status: "waiting",
    action: "retry_reading",
    stage: "queued",
    message:
      "Retry accepted for the retained reading. Saved work is unchanged.",
    reading_file_id: file.id,
    review_file_id: file.id,
  }
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (options?.method === "POST") {
      posts.push(url)
      if (
        url !==
        `/api/financial/statement-import/batches/${batch.id}/files/older-reading/retry?case_id=case`
      )
        throw Error(
          "Retry must use the original batch source, never a filename or retained reading ID."
        )
      return new Promise((resolve) => {
        retryResolve = resolve
      })
    }
    if (url.startsWith("/api/evidence/engine/jobs?")) {
      jobReads++
      return [
        {
          id: "failed-reading-job",
          case_id: "case",
          batch_id: null,
          evidence_file_id: file.id,
          file_name: file.original_filename,
          job_type: "pdf_review",
          resumable: false,
          status: retried ? "extracting_text" : "failed",
          progress: retried ? 0.4 : 0,
          error_message: retried ? null : "Synthetic reading failure",
          file_size: 100,
          created_at: "2026-09-25T10:00:00Z",
          updated_at: "2026-09-25T10:00:01Z",
        },
      ]
    }
    if (url.includes(`/batches/${batch.id}?`))
      return {
        ...batch,
        status: retried && !completed ? "preparing" : "review",
        reading_job_ids: ["failed-reading-job"],
        files: [
          {
            ...batch.files[0],
            file_id: file.id,
            status: completed ? "checked" : retried ? "processing" : "error",
            error: retried ? undefined : "Synthetic reading failure",
            recovery: retried ? receipt : null,
          },
        ],
      }
    return original(url, options)
  })
  mount(`/cases/case/financial?view=statements&batch=${batch.id}`)
  await page
    .getByText("PDF reading jobs · pause or resume a reading", { exact: true })
    .click()
  const reading = await screen.findByRole("group", {
    name: `Financial statement reading: ${file.original_filename}`,
  })
  const details = reading.closest("details")!
  expect(
    within(reading).queryByRole("button", { name: "Clear" })
  ).not.toBeInTheDocument()
  await page.getByRole("button", { name: "Retry", exact: true }).click()
  expect(within(reading).getByRole("button", { name: "Retry" })).toBeDisabled()
  expect(within(details).getByRole("status")).toHaveTextContent(
    "Requesting retry"
  )
  expect(posts).toHaveLength(1)
  await act(async () => {
    retried = true
    retryResolve(receipt)
  })
  expect(
    await within(details).findByText(
      `${file.original_filename}: ${receipt.message}`
    )
  ).toBeVisible()
  expect(await within(reading).findByText("Extracting Text")).toBeVisible()
  expect(jobReads).toBeGreaterThan(1)
  await page.screenshot({ path: "/private/tmp/loupe-reading-job-retry-wide.png", element: details })
  completed = true
  await page.getByRole("button", { name: "Refresh batch", exact: true }).click()
  await page.getByText("File processing (1)", { exact: true }).click()
  await page
    .getByRole("button", { name: "Open file review", exact: true })
    .click()
  await waitFor(() => expect(screen.getByText(proposal.reading_failure)).toBeVisible())
  expect(screen.getByLabelText("Uploaded statement")).toHaveValue(file.id)
  expect(screen.getByLabelText("Current route")).toHaveTextContent(
    `reviewFile=${file.id}`
  )
  await page
    .getByRole("button", { name: "Back to processing batch", exact: true })
    .click()
  expect(
    await screen.findByRole("region", { name: "Financial processing batch" })
  ).toBeVisible()
  expect(screen.getByLabelText("Current route")).toHaveTextContent(
    `batch=${batch.id}`
  )
  await page.getByText("File processing (1)", { exact: true }).click()
  expect(screen.getByText(receipt.message)).toBeVisible()
  expect(posts).toEqual([
    `/api/financial/statement-import/batches/${batch.id}/files/older-reading/retry?case_id=case`,
  ])
})

for (const sourceState of ["removed", "missing"] as const) {
  it(`retains the exact ${sourceState} failed source and return path with the full file register already loaded`, async () => {
    const failedId = `${sourceState}-original`
    const independent = {
      ...file,
      id: "independent-same-name",
      created_at: "2026-09-26T12:00:00Z",
    }
    const unavailableBatch = {
      ...batch,
      files: [
        {
          ...batch.files[0],
          source_id: failedId,
          file_id: failedId,
          review_file_id: failedId,
          error: "Statement not found in this case.",
        },
      ],
    }
    const original = vi.mocked(fetchAPI).getMockImplementation()!
    vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
      if (options?.method)
        throw Error(
          "Opening an unavailable review must not change or reprocess any source."
        )
      if (url.startsWith("/api/evidence?"))
        return {
          files: [
            ...(sourceState === "removed"
              ? [
                  {
                    ...file,
                    id: failedId,
                    financial_removed: true,
                    created_at: "2026-09-25T12:00:00Z",
                  },
                ]
              : []),
            independent,
            otherFile,
          ],
        } as never
      if (url.includes(`/batches/${batch.id}?`))
        return unavailableBatch as never
      if (url.includes(`/statement-import/${failedId}?`))
        throw new ApiError("Statement not found in this case.", 404)
      if (url.includes(`/statement-import/${independent.id}?`))
        throw Error(
          "An independent same-name upload must never be substituted."
        )
      return original(url, options)
    })
    await page.viewport(sourceState === "removed" ? 1360 : 480, 1000)
    const first = mount()
    // Await the populated full register, not only its loading shell. The removed
    // source is already cached when batch navigation opens the selected review.
    await screen.findByRole("button", {
      name: `Review ${file.original_filename}`,
    })
    fireEvent.click(screen.getByRole("button", { name: "Processing batches" }))
    fireEvent.click(
      await screen.findByRole("button", { name: "Open batch batch-or" })
    )
    fireEvent.click(
      await screen.findByRole("button", { name: "Open file review" })
    )
    const title =
      sourceState === "removed"
        ? "This source was removed from Financial"
        : "Statement review unavailable"
    expect(await screen.findByRole("heading", { name: title })).toBeVisible()
    expect(screen.getByLabelText("Uploaded statement")).toHaveValue(failedId)
    expect(screen.getByText(`Source reference: ${failedId}`)).toBeVisible()
    expect(screen.getByLabelText("Selected statement review")).toHaveFocus()
    expect(
      screen.getByRole("button", { name: "Back to processing batch" })
    ).toBeVisible()
    expect(
      screen.getByRole("link", { name: "Open source location in Evidence" })
    ).toHaveAttribute(
      "href",
      `/cases/case/evidence?file=${failedId}&from=financial`
    )
    expect(screen.getByLabelText("Current route")).toHaveTextContent(
      `reviewFile=${failedId}`
    )
    expect(screen.getByLabelText("Current route")).toHaveTextContent(
      `returnBatch=${batch.id}`
    )
    expect(
      screen.queryByRole("button", { name: "Continue last statement review" })
    ).not.toBeInTheDocument()
    expect(
      screen.queryByText("Read the statement again")
    ).not.toBeInTheDocument()
    expect(
      screen.queryByText(`Synthetic original: ${independent.id}`)
    ).not.toBeInTheDocument()
    await page.screenshot({
      path: `/private/tmp/loupe-batch-${sourceState}-review.png`,
    })
    await page.screenshot({
      element: screen.getByLabelText("Selected statement review"),
      path: `/private/tmp/loupe-batch-${sourceState}-review-detail.png`,
    })
    const destination = screen.getByLabelText("Current route").textContent!
    first.unmount()
    mount(`/cases/case/financial${destination}`)
    expect(await screen.findByRole("heading", { name: title })).toBeVisible()
    expect(screen.getByLabelText("Current route")).toHaveTextContent(
      `reviewFile=${failedId}`
    )
    fireEvent.click(
      screen.getByRole("button", { name: "Back to processing batch" })
    )
    expect(
      await screen.findByRole("region", { name: "Financial processing batch" })
    ).toBeVisible()
    expect(screen.getByLabelText("Current route")).toHaveTextContent(
      `batch=${batch.id}`
    )
    expect(
      vi.mocked(fetchAPI).mock.calls.every(([, options]) => !options?.method)
    ).toBe(true)
    expect(
      vi
        .mocked(fetchAPI)
        .mock.calls.some(([url]) =>
          url.includes(`/statement-import/${independent.id}?`)
        )
    ).toBe(false)
    if (sourceState === "removed")
      expect(
        vi
          .mocked(fetchAPI)
          .mock.calls.some(([url]) =>
            url.includes(`/statement-import/${failedId}?`)
          )
      ).toBe(false)
  })
}


it("opens file review from the actual page after selecting Processing batches and returns to its batch", async () => {
  mount()
  fireEvent.click(screen.getByRole("button", { name: "Processing batches" }))
  fireEvent.click(await screen.findByRole("button", { name: "Open batch batch-or" }))
  fireEvent.click(await screen.findByRole("button", { name: "Open file review" }))
  expect(await screen.findByText(proposal.reading_failure)).toBeVisible()
  expect(screen.getByLabelText("Uploaded statement")).toHaveValue(file.id)
  expect(screen.getByRole("button", { name: "Statement files" })).toHaveAttribute("aria-pressed", "true")
  expect(screen.queryByRole("region", { name: "Financial processing batch" })).not.toBeInTheDocument()
  const review = screen.getByLabelText("Selected statement review")
  expect(review).toHaveFocus()
  expect(within(review).getByText(`Synthetic original: ${file.id}`)).toBeVisible()
  await page.screenshot({ path: "/private/tmp/loupe-batch-file-review-wide.png" })
  fireEvent.click(screen.getByRole("button", { name: "Back to processing batch" }))
  expect(await screen.findByRole("region", { name: "Financial processing batch" })).toBeVisible()
  expect(screen.getByLabelText("Current route")).toHaveTextContent(`batch=${batch.id}`)
  fireEvent.click(screen.getByRole("button", { name: "Open file review" }))
  expect(await screen.findByText(proposal.reading_failure)).toBeVisible()
  fireEvent.click(screen.getByRole("button", { name: "Browser back" }))
  expect(await screen.findByRole("region", { name: "Financial processing batch" })).toBeVisible()
  fireEvent.click(screen.getByRole("button", { name: "Back to all statements" }))
  expect(await screen.findByRole("heading", { name: "Files in Financial" })).toBeVisible()
  expect(screen.getByLabelText("Selected statement review")).not.toBeVisible()
  expect(screen.queryByRole("region", { name: "Financial processing batch" })).not.toBeInTheDocument()
  expect(vi.mocked(fetchAPI).mock.calls.every(([, options]) => !options?.method)).toBe(true)
})

it("reopens the exact routed file after refresh and returns to the retained batch review filter", async () => {
  useStatementWorkspace.getState().select("anonymous:case", "different-file")
  mount(`/cases/case/financial?view=statements&files=1&reviewFile=${file.id}&returnBatch=${batch.id}&returnBatchCheck=balance`)
  expect(await screen.findByText(proposal.reading_failure)).toBeVisible()
  expect(screen.getByLabelText("Uploaded statement")).toHaveValue(file.id)
  await page.viewport(480, 900)
  expect(screen.getByRole("button", { name: "Back to processing batch" })).toBeVisible()
  await page.screenshot({ path: "/private/tmp/loupe-batch-file-review-narrow.png" })
  fireEvent.change(screen.getByLabelText("Uploaded statement"), { target: { value: otherFile.id } })
  await waitFor(() => expect(screen.getByLabelText("Current route")).toHaveTextContent(`reviewFile=${otherFile.id}`))
  expect(await screen.findByText(`Synthetic original: ${otherFile.id}`)).toBeVisible()
  fireEvent.click(screen.getByRole("button", { name: "All files & imports" }))
  expect(await screen.findByRole("heading", { name: "Files in Financial" })).toBeVisible()
  expect(screen.getByLabelText("Current route")).not.toHaveTextContent("reviewFile=")
  fireEvent.click(screen.getByRole("button", { name: "Continue last statement review" }))
  expect(await screen.findByText(`Synthetic original: ${otherFile.id}`)).toBeVisible()
  expect(screen.getByLabelText("Current route")).toHaveTextContent(`reviewFile=${otherFile.id}`)
  fireEvent.click(screen.getByRole("button", { name: "Back to processing batch" }))
  await screen.findByRole("region", { name: "Financial processing batch" })
  await waitFor(() => expect(screen.getByLabelText("Current route")).toHaveTextContent("batchCheck=balance"))
  expect(fetchAPI).toHaveBeenCalledWith(expect.stringContaining(`/${batch.id}?case_id=case&offset=0&only_problems=false&review_group=balance`))
  fireEvent.click(screen.getByRole("button", { name: "Open file review" }))
  expect(await screen.findByText(proposal.reading_failure)).toBeVisible()
  fireEvent.click(screen.getByRole("button", { name: "Remove imports…" }))
  expect(await screen.findByRole("heading", { name: "Remove imports or start again" })).toBeVisible()
  expect(screen.getByLabelText("Current route")).not.toHaveTextContent("files=1")
  expect(screen.getByLabelText("Selected statement review")).not.toBeVisible()
  fireEvent.click(screen.getByRole("button", { name: "Statement files" }))
  expect(await screen.findByRole("heading", { name: "Files in Financial" })).toBeVisible()
})

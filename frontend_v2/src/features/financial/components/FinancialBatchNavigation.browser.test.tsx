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
  expect(fetchAPI).toHaveBeenCalledWith(expect.stringContaining(`/${batch.id}?case_id=case&offset=0&only_problems=false&review_group=balance`), expect.objectContaining({ timeout: 60000 }))
  fireEvent.click(screen.getByRole("button", { name: "Open file review" }))
  expect(await screen.findByText(proposal.reading_failure)).toBeVisible()
  fireEvent.click(screen.getByRole("button", { name: "Remove imports…" }))
  expect(await screen.findByRole("heading", { name: "Remove imports or start again" })).toBeVisible()
  expect(screen.getByLabelText("Current route")).not.toHaveTextContent("files=1")
  expect(screen.getByLabelText("Selected statement review")).not.toBeVisible()
  fireEvent.click(screen.getByRole("button", { name: "Statement files" }))
  expect(await screen.findByRole("heading", { name: "Files in Financial" })).toBeVisible()
})


it.each([1280, 390])("saves ready balance-only reviews above warnings, opens Accounts and returns to the same batch at %ipx", async (width) => {
  await page.viewport(width, 1000)
  const original = vi.mocked(fetchAPI).getMockImplementation()!
  let accepted = false
  let resolveSave: (value: unknown) => void = () => {}
  const posts: { url: string, body: unknown }[] = []
  const summary = { total: 14, available: 7, blocked: 6, imported: 1, pending_import: 0, skipped: 0, duplicate_ignored: 0, assigned: 0, other: 0, available_with_payments: 0, available_no_activity: 7, available_other: 0 }
  const operation = {
    id: "synthetic-save", status: "complete", created_at: "2026-09-25T10:00:00Z", statement_count: 7,
    pending: 0, failed: 0, imported: 7, already_present: 0, duplicate_ignored: 0, transaction_count: 0, incomplete_count: 0,
    outcomes: Array.from({length:7}, (_, i) => ({ item_id: `saved-${i}`, filename: `Synthetic balance ${i}.pdf`, status: "imported", period_start: "2026-01-01", period_end: "2026-01-31" })),
  }
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (options?.method) {
      expect(url).toBe(`/api/financial/statement-import/batches/${batch.id}/confirm?case_id=case`)
      expect(options.method).toBe("POST")
      posts.push({url, body:options.body})
      return new Promise((resolve) => { resolveSave = resolve })
    }
    if (url.includes(`/batches/${batch.id}/imported-transactions?`)) {
      expect(url).toContain("operation_id=synthetic-save")
      return {case_id:"case", batch_id:batch.id, revision:"c".repeat(64), source_document_ids:["saved-source"], account_ids:["eur-account"], statement_count:7, transaction_count:0, start_date:"2026-01-01", end_date:"2026-01-31"}
    }
    if (url.startsWith("/api/financial/account-history?")) {
      expect(url).toContain("account_ids=eur-account")
      expect(url).not.toContain("start_date=")
      return {case_id:"case",applied:false,groups:[{key:"eur-account:EUR:asset",account_id:"eur-account",currency:"EUR",balance_kind:"asset",label:"Synthetic saved EUR account",periods:[{id:"saved-period",source_document_id:"saved-source",evidence_file_id:"saved-file",filename:"Synthetic balance.pdf",start:"2026-01-01",end:"2026-01-31",opening_minor:"12345",closing_minor:"12345",status:"confirmed_no_activity",assessment_current:true,transaction_count:0,undated_count:0,activity:[]}]}]}
    }
    if (url.includes(`/batches/${batch.id}?`)) return {
      ...batch, files:Array.from({length:11}, (_, i)=>({source_id:`source-${i}`,file_id:`file-${i}`, filename:`Synthetic file ${i}.pdf`,status:"checked"})),
      counts:{ready:accepted?0:7,attention:6,imported:accepted?8:1},
      available_statements:accepted?0:7,available_records:0,available_transactions:0,
      statement_summary:accepted?{...summary,available:0,imported:8,available_no_activity:0}:summary,
      review_summary:{blocked_statements:6,importable_with_checks:0,imported_with_checks:1,unchecked_balance_statements:0,
        groups:Array.from({length:18},(_,i)=>({id:`reason-${i}`,label:`Synthetic reason ${i}`,explanation:"Compare the original statement and correct the identified reading.",statement_count:6,check_count:12,blocked_statements:6,importable_statements:0,imported_statements:0}))},
      total:1, items:[], operations:accepted?[operation]:[],
    }
    return original(url, options)
  })
  mount(`/cases/case/financial?view=statements&batch=${batch.id}&batchCheck=reason-0`)
  const action = await screen.findByRole("button", {name:"Save 7 statements to Financial"})
  expect(posts).toHaveLength(0)
  expect(screen.getByText("11 of 11 files read")).toBeVisible()
  expect(screen.getByText("14 prepared statement reviews")).toBeVisible()
  expect(screen.getByText(/These statements are confirmed to contain no payments/)).toBeVisible()
  expect(action.getBoundingClientRect().bottom).toBeLessThan(1000)
  expect(action.getBoundingClientRect().top).toBeLessThan(screen.getByRole("region",{name:"Review checks by reason"}).getBoundingClientRect().top)
  await page.screenshot({path:`/private/tmp/loupe-batch-ready-${width}.png`})
  await page.getByRole("button", {name:"Save 7 statements to Financial",exact:true}).click()
  await waitFor(()=>expect(posts).toHaveLength(1))
  expect(posts[0].body).toEqual({request_id:expect.any(String),expected_ready_revision:"a".repeat(64)})
  expect(screen.getByRole("button",{name:"Submitting save request…"})).toBeDisabled()
  await act(async()=>{accepted=true;resolveSave({request_id:"synthetic-save"})})
  await screen.findByRole("region",{name:"Import results"})
  const accounts = await screen.findByRole("button",{name:"View saved statements in Accounts"})
  expect(accounts.getBoundingClientRect().top).toBeLessThan(screen.getByRole("region",{name:"Review checks by reason"}).getBoundingClientRect().top)
  await page.getByRole("button",{name:"View saved statements in Accounts",exact:true}).click()
  await waitFor(()=>expect(screen.getByRole("button",{name:"Review accounts"})).toHaveAttribute("aria-pressed","true"))
  expect(screen.getByLabelText("Current route")).toHaveTextContent(`accounts=1&returnBatch=${batch.id}`)
  expect(screen.getByText(/Saved statements are recorded with their accounts/).parentElement).toHaveFocus()
  await screen.findByRole("region", {name:"Account balances and activity"})
  await waitFor(() => expect(screen.getByRole("region", {name:"Accounts from saved statements"})).toHaveTextContent("2026-01-01"))
  expect(screen.getByRole("region", {name:"Accounts from saved statements"})).toHaveTextContent("123.45 EUR")
  expect(screen.getByRole("region", {name:"Accounts from saved statements"})).toHaveTextContent("7 saved statements · 1 account · 0 imported transactions")
  expect(screen.getByRole("button", {name:"Show all accounts in this case"})).toBeVisible()
  await page.getByRole("button",{name:"Back to processing batch",exact:true}).click()
  await screen.findByRole("region",{name:"Financial processing batch"})
  expect(screen.getByLabelText("Current route")).toHaveTextContent(`batch=${batch.id}`)
  expect(screen.getByRole("region",{name:"Import results"})).toBeVisible()
  expect(screen.getByLabelText("Current route")).toHaveTextContent("batchCheck=reason-0")
  expect(posts).toHaveLength(1)
})

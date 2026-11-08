import { render, screen, fireEvent, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { it, expect, vi, afterEach } from "vitest"
import { LedgerExportButton } from "./LedgerExportButton"

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  localStorage.clear()
})

const packet = {
  completeness: "incomplete_expert_packet",
  byte_count: 2097152,
  sentence: "This export is not a complete expert packet. Complete: Custody and decisions. Incomplete: Measured validation.",
  parts: [
    { label: "Custody and decisions", holds: true },
    { label: "Measured validation", holds: false },
  ],
}
const summary = {
  archive_bytes: 2097152,
  snapshot_bytes: 5000,
  rows: 10861,
  generated_at: "2026-11-05T10:15:00+00:00",
  filename: "ledger-export.zip",
  packet,
  audit_events: { event_count: 262753, head_sha256: "a".repeat(64), status: "verified_recorded_chain" },
  audit_parts: 90,
}
const running = {
  id: "a".repeat(32),
  kind: "export",
  status: "running",
  phase: "Checking and packing the audit events",
  step: 1,
  steps: 4,
  done: 120000,
  total: 262753,
  created_at: "2026-11-05T10:00:00+00:00",
}
const completed = { ...running, status: "completed", phase: "Finished", summary }

function server(answers: Record<string, unknown>[], start: { status?: number; body?: unknown } = {}) {
  const calls: { url: string; method: string; body: Record<string, unknown> | null }[] = []
  let next = 0
  const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(async (url, options) => {
    const method = options?.method ?? "GET"
    calls.push({ url: String(url), method, body: options?.body ? JSON.parse(options.body as string) : null })
    if (method === "POST")
      return new Response(JSON.stringify(start.body ?? answers[0]), {
        status: start.status ?? 200,
        headers: { "content-type": "application/json" },
      })
    const answer = answers[Math.min(next++, answers.length - 1)]
    return new Response(JSON.stringify(answer), { headers: { "content-type": "application/json" } })
  })
  return { calls, fetch }
}

function mount(
  tableView?: import("../lib/ledger-table-view").LedgerTableView,
  params: import("../hooks/use-ledger-transactions").LedgerQueryParams = {
    accountId: "account-a",
    startDate: "2026-01-01",
    endDate: "2026-01-31",
  }
) {
  const client = new QueryClient()
  return render(
    <QueryClientProvider client={client}>
      <LedgerExportButton caseId="case-a" tableView={tableView} params={params} />
    </QueryClientProvider>
  )
}

const download = (name = "Download ledger snapshot") => fireEvent.click(screen.getByRole("button", { name }))
const started = (calls: { method: string; body: Record<string, unknown> | null }[]) =>
  calls.filter((call) => call.method === "POST")

it("starts nothing on opening the page", async () => {
  const { calls } = server([running])
  mount()
  await new Promise((resolve) => setTimeout(resolve, 20))
  expect(calls).toEqual([])
})

it("starts a background run of the applied scope and shows a stated progress line", async () => {
  const { calls } = server([running])
  mount()
  download()
  expect(await screen.findByText(/Step 1 of 4: Checking and packing the audit events \(120,000 of 262,753\)/)).toBeVisible()
  expect(started(calls)[0].body).toMatchObject({
    kind: "export",
    account_id: "account-a",
    start_date: "2026-01-01",
    end_date: "2026-01-31",
    privilege_marking: "unmarked",
    include_case_financial_history: false,
    fresh: false,
  })
  expect(screen.getByRole("button", { name: "Preparing ledger export…" })).toBeDisabled()
  expect(screen.queryByRole("link")).toBeNull()
})

it("offers the file when the run is ready, with what it holds", async () => {
  server([completed])
  mount()
  download()
  const link = await screen.findByRole("link", { name: "Download the export (2.0 MB)" })
  expect(link.getAttribute("href")).toContain(`whole-case-runs/${running.id}/files/ledger-export.zip`)
  expect(screen.getByText(/Ready: 10,861 rows, 262,753 audit events, read at 2026-11-05 10:15 UTC/)).toBeVisible()
})

it("survives leaving the page: the same run is followed, and nothing is started again", async () => {
  const { calls } = server([running, running, running, completed])
  const page = mount()
  download()
  await screen.findByText(/Step 1 of 4/)
  page.unmount()
  const posts = started(calls).length
  mount()
  expect(await screen.findByRole("link", { name: /Download the export/ }, { timeout: 8000 })).toBeVisible()
  expect(started(calls).length).toBe(posts)
})

it("asks for a fresh reading only when told to", async () => {
  const { calls } = server([completed])
  mount()
  download()
  fireEvent.click(await screen.findByRole("button", { name: "Read the rows again" }))
  await waitFor(() => expect(started(calls).length).toBe(2))
  expect(started(calls)[1].body?.fresh).toBe(true)
})

it("names a refusal from the run on the page and offers no file", async () => {
  const words = "Audit event 7 alone exceeds the 64 MiB limit of one archive member. No partial export was produced."
  server([{ ...running, status: "failed", error: words }])
  mount()
  download()
  expect(await screen.findByRole("alert")).toHaveTextContent(words)
  expect(screen.queryByRole("link")).toBeNull()
})

it("names a refusal at the start on the page", async () => {
  server([], { status: 422, body: { detail: "6 whole-case runs are already waiting on this server." } })
  mount()
  download()
  expect(await screen.findByRole("alert")).toHaveTextContent("already waiting")
})

it("a stopped run says so, offers nothing, and can be prepared again", async () => {
  const words = "The server restarted while this ran. Nothing partial was offered. Run it again."
  const { calls } = server([{ ...running, status: "stopped", error: words }])
  mount()
  download()
  expect(await screen.findByRole("alert")).toHaveTextContent(words)
  expect(screen.queryByRole("link")).toBeNull()
  fireEvent.click(screen.getByRole("button", { name: "Prepare it again" }))
  await waitFor(() => expect(started(calls).length).toBe(2))
})

it("a run past its keeping time goes back to offering a new one", async () => {
  const first = server([running])
  const page = mount()
  download()
  await screen.findByText(/Step 1 of 4/)
  page.unmount()
  first.fetch.mockImplementation(
    async () => new Response(JSON.stringify({ detail: "Whole-case run not found." }), { status: 404 })
  )
  mount()
  await waitFor(() => expect(screen.getByRole("button", { name: "Download ledger snapshot" })).toBeEnabled())
  expect(localStorage.length).toBe(0)
})

it("sends each option that was chosen, and only those", async () => {
  const { calls } = server([running])
  mount()
  fireEvent.click(screen.getByRole("checkbox", { name: /Include wider case financial review history/ }))
  fireEvent.click(screen.getByLabelText("Include original source files with fresh hash checks"))
  fireEvent.click(screen.getByLabelText("Include a paginated PDF report"))
  fireEvent.change(screen.getByLabelText("Export marking"), { target: { value: "confidential" } })
  expect(screen.getByText(/complete referenced files/)).toBeVisible()
  download()
  await screen.findByText(/Step 1 of 4/)
  expect(started(calls)[0].body).toMatchObject({
    include_case_financial_history: true,
    include_source_files: true,
    include_pdf: true,
    privilege_marking: "confidential",
  })
})

it("a different choice of options has its own run", async () => {
  server([completed])
  mount()
  download()
  await screen.findByRole("link", { name: /Download the export/ })
  fireEvent.click(screen.getByRole("checkbox", { name: /Include wider case financial review history/ }))
  await waitFor(() => expect(screen.queryByRole("link")).toBeNull())
})

it("captures the full table settings in the run's request", async () => {
  const view = { search: "Office cost", currency: "GBP", direction: "debit", proof: "p3", sort: "amount-desc" }
  const { calls } = server([completed])
  mount(view)
  download("Download this table view")
  await screen.findByRole("link", { name: /Download the export/ })
  expect(JSON.parse(started(calls)[0].body?.table_view as string)).toEqual(view)
})

it("a PDF over one report's size opens the numbered parts in place of the refusal", async () => {
  const words = "PDF reports support up to 2,000 captured readings."
  const { calls } = server([{ ...running, status: "failed", error: words }])
  mount()
  fireEvent.click(screen.getByLabelText("Include a paginated PDF report"))
  download()
  await waitFor(() => expect(calls.filter((call) => call.method === "POST" && call.body?.kind === "pdf").length).toBe(1))
  expect(screen.queryByText(words)).toBeNull()
})

it("a start refused for a PDF over one report opens the numbered parts straight away, with their progress", async () => {
  const words = "PDF reports support up to 2,000 captured readings. Narrow the export scope; no partial report was generated."
  const calls: { method: string; body: Record<string, unknown> | null }[] = []
  vi.spyOn(globalThis, "fetch").mockImplementation(async (url, options) => {
    const method = options?.method ?? "GET"
    const body = options?.body ? JSON.parse(options.body as string) : null
    calls.push({ method, body })
    if (method === "POST" && body?.kind === "export")
      return new Response(JSON.stringify({ detail: words }), { status: 422, headers: { "content-type": "application/json" } })
    return new Response(JSON.stringify({ ...running, kind: "pdf" }), { headers: { "content-type": "application/json" } })
  })
  mount()
  fireEvent.click(screen.getByLabelText("Include a paginated PDF report"))
  download()
  await waitFor(() => expect(calls.filter((call) => call.method === "POST" && call.body?.kind === "pdf").length).toBe(1))
  expect(await screen.findByText(/Step 1 of 4: Checking and packing the audit events \(120,000 of 262,753\)/)).toBeTruthy()
  expect(screen.getByText(/no export archive was produced/)).toBeTruthy()
  expect(screen.queryByRole("alert")).toBeNull()
})

it("never asks for a run before it has one", async () => {
  const { calls } = server([completed])
  mount()
  download()
  await screen.findByRole("link", { name: /Download the export/ })
  expect(calls.filter((call) => call.url.includes("whole-case-runs/null"))).toEqual([])
})

it("a PDF refused on a table view stays on the page, which has no numbered parts", async () => {
  const words = "PDF reports support up to 2,000 captured readings."
  const { calls } = server([{ ...running, status: "failed", error: words }])
  mount({ search: "Office cost", currency: "GBP", direction: "debit", proof: "p3", sort: "amount-desc" })
  fireEvent.click(screen.getByLabelText("Include a PDF in the table-view export"))
  download("Download this table view")
  expect(await screen.findByText(words)).toBeTruthy()
  expect(calls.some((call) => call.body?.kind === "pdf")).toBe(false)
})

it("states the expert packet parts the server reported for this export, with its size", async () => {
  server([completed])
  mount()
  expect(screen.queryByText(/not a complete expert packet/)).toBeNull()
  download()
  const result = await screen.findByLabelText("Expert packet parts in this export")
  expect(result).toHaveTextContent("not a complete expert packet")
  expect(result).toHaveTextContent("Custody and decisions: complete")
  expect(result).toHaveTextContent("Measured validation: incomplete")
  expect(result).toHaveTextContent("Download size: 2.0 MB")
})

it("makes no packet claim when a run carries no statement of its parts", async () => {
  server([{ ...completed, summary: { ...summary, packet: null } }])
  mount()
  download()
  await screen.findByRole("link", { name: /Download the export/ })
  expect(screen.queryByLabelText("Expert packet parts in this export")).toBeNull()
})

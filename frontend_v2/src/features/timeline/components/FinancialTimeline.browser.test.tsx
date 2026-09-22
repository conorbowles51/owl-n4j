import "@/styles/globals.css"
import "@/features/financial/financial-workspace.css"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter, Routes, Route } from "react-router-dom"
import {
  render,
  screen,
  fireEvent,
  within,
  cleanup,
  waitFor,
} from "@testing-library/react"
import { beforeEach, afterEach, expect, it, vi } from "vitest"
import { page } from "vitest/browser"
import { fetchAPI } from "@/lib/api-client"
import { LedgerRowBrowser } from "@/features/financial/components/LedgerRowBrowser"
import { FinancialFindings } from "@/features/financial/components/FinancialFindings"
import { paymentFixture } from "@/features/financial/lib/payment-fixture.test-support"
import { useFinancialDraftStore } from "@/features/financial/stores/financial-drafts"
import { useTimelineStore } from "../stores/timeline.store"
import { TimelinePage } from "./TimelinePage"
import type { TimelineEvent } from "../api"
import { AddToTimelineDialog } from "./AddToTimelineDialog"
vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(),
}))
vi.mock(
  "@/features/financial/hooks/use-financial-access",
  async (original) => ({
    ...(await original<
      typeof import("@/features/financial/hooks/use-financial-access")
    >()),
    useFinancialAccess: () => ({ canEdit: true }),
  })
)
vi.mock("@/features/financial/components/SourceCustodyPanel", () => ({
  SourceCustodyPanel: () => null,
}))
const payment = {
  ...paymentFixture,
  case_id: "case",
  key: "payment",
  description: "Supplier transfer",
  amount_minor: "12500",
  currency: "USD",
  transaction_date: "2021-02-08",
  ordering_date: "2021-02-08",
}
const undated = {
  ...payment,
  key: "undated",
  description: "Supplier payment without date",
  transaction_date: null,
  posted_date: null,
  value_date: null,
  effective_date: null,
}
const finding = {
  id: "finding",
  case_id: "case",
  title: "Check supplier invoice",
  body: "The transfer needs an invoice.",
  entry_type: "note",
  tags: ["financial", "financial-workspace", "financial-observation"],
  version: 1,
  links: [],
  created_at: "2026-09-22T12:00:00Z",
}
const observation = {
  ...finding,
  id: "observation",
  title: "Possible duplicate",
  tags: ["financial", "financial-workspace", "financial-question"],
}
type Body = { source_kind: string; source_ids: string[]; event_date?: string }
let saved: TimelineEvent[] = []
let failSave = false
let calls: Body[] = []
const fixtureEvent = (body: Body): TimelineEvent => {
  const paymentSource = body.source_kind === "transaction"
  const entry = body.source_ids[0] === "observation" ? observation : finding
  return {
    key: `timeline-entry:${body.source_ids[0]}`,
    name: paymentSource ? payment.description : entry.title,
    type: paymentSource
      ? "Transaction"
      : entry.id === "observation"
        ? "Observation"
        : "Finding",
    date: paymentSource ? "2021-02-08" : body.event_date!,
    time: null,
    amount: paymentSource ? "125.00 USD · Money out" : null,
    summary: paymentSource
      ? "Synthetic statement.pdf · TX-SUPPLIER"
      : entry.body,
    notes: null,
    connections: [],
    source: {
      kind: paymentSource ? "transaction" : "workspace_entry",
      id: body.source_ids[0],
      state: "current",
      label: paymentSource
        ? "Synthetic statement.pdf · TX-SUPPLIER"
        : entry.title,
      date_basis: paymentSource
        ? "Transaction date"
        : "Event date chosen by investigator",
    },
  }
}
beforeEach(() => {
  saved = []
  calls = []
  failSave = false
  useFinancialDraftStore.setState({ drafts: {} })
  useTimelineStore.getState().clearAllFilters([])
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (url.includes("/api/timeline/entries")) {
      const body = options?.body as Body
      if (!body)
        return { case_id: "case", events: saved, next_offset: null } as never
      const event = fixtureEvent(body)
      const present = saved.some((row) => row.key === event.key)
      const missing = body.source_ids.includes("undated") ? 1 : 0
      if (url.includes("preview"))
        return {
          case_id: "case",
          revision: "a".repeat(64),
          ready: present ? 0 : 1,
          already_added: present ? 1 : 0,
          undated: missing,
          rows: [
            {
              source_id: body.source_ids[0],
              name: event.name,
              status: present ? "already_added" : "ready",
              event,
            },
            ...(missing
              ? [
                  {
                    source_id: "undated",
                    name: undated.description,
                    status: "undated",
                    event: null,
                  },
                ]
              : []),
          ],
        } as never
      calls.push(body)
      if (failSave) {
        failSave = false
        throw Error(
          "The selection changed since review. Refresh the preview before adding it."
        )
      }
      if (!present) saved.push(event)
      return {
        case_id: "case",
        added: present ? 0 : 1,
        already_added: present ? 1 : 0,
        undated: missing,
        event_keys: [event.key],
      } as never
    }
    if (url.startsWith("/api/timeline?"))
      return { events: [], count: 0, total: 0, next_cursor: null } as never
    if (url.includes("financial-payment-links"))
      return { case_id: "case", entries: [], total: 0 } as never
    if (url.includes("category-library") || url.includes("ledger-categories"))
      return { case_id: "case", categories: [] } as never
    if (url.includes("ledger-accounts"))
      return { case_id: "case", accounts: [], total: 0 } as never
    if (url.includes("/api/workspace/case/entries/"))
      return {
        ...(url.includes("/observation") ? observation : finding),
        review_state: "accepted",
        migration_metadata: {},
        needs_migration_review: false,
      } as never
    if (url.includes("/api/workspace/case/entries"))
      return { entries: [finding, observation], total: 2 } as never
    if (url.includes("/ledger/payment/source"))
      return {
        case_id: "case",
        transaction_id: payment.key,
        ref_id: payment.ref_id,
        transaction: payment,
        source_document_id: payment.source_document_id,
        evidence_file_id: "11111111-1111-4111-8111-111111111111",
        filename: "Synthetic statement.pdf",
        sha256_at_ingestion: "a".repeat(64),
        recorded_digest_matches: true,
        file_bytes_verified: false,
        locator_state: "missing",
        locator: null,
        ledger_status: "admitted",
        superseded_by_id: null,
        limitation: "Test fixture",
      } as never
    throw Error(`Unexpected fixture request: ${url}`)
  })
})
afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})
function renderJourney(mode = "transactions") {
  render(
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: {
            queries: { retry: false },
            mutations: { retry: false },
          },
        })
      }
    >
      <MemoryRouter initialEntries={[`/cases/case/financial?view=${mode}`]}>
        <div className="h-screen bg-background text-foreground p-4">
          <Routes>
            <Route
              path="/cases/:id/financial"
              element={
                mode === "transactions" ? (
                  <LedgerRowBrowser
                    investigation
                    transactions={[payment, undated]}
                    exportContext={{ caseId: "case", params: {} }}
                  />
                ) : (
                  <FinancialFindings caseId="case" />
                )
              }
            />
            <Route path="/cases/:id/timeline" element={<TimelinePage />} />
          </Routes>
        </div>
      </MemoryRouter>
    </QueryClientProvider>
  )
}
it("adds payments, explains skipped dates, opens Timeline and original, returns with filters and selection and prevents duplicates", async () => {
  await page.viewport(1440, 1000)
  renderJourney()
  fireEvent.change(screen.getByLabelText("Search payments"), {
    target: { value: "Supplier" },
  })
  fireEvent.click(
    screen.getByRole("checkbox", { name: /Select Supplier transfer on/ })
  )
  fireEvent.click(
    screen.getByRole("checkbox", {
      name: /Select Supplier payment without date on/,
    })
  )
  fireEvent.click(screen.getByRole("button", { name: "Add to Timeline" }))
  fireEvent.click(
    screen.getByRole("button", { name: "Review Timeline entries" })
  )
  await screen.findByText(
    "1 ready · 0 already added · 1 without a payment date"
  )
  fireEvent.click(screen.getByRole("button", { name: "Add 1 to Timeline" }))
  await screen.findByText("1 added to Timeline.")
  useTimelineStore.setState({
    searchTerm: "stale filter",
    selectedTypes: new Set(["Email"]),
    dateRange: { start: "2025-01-01", end: "2025-02-01" },
  })
  fireEvent.click(screen.getByRole("button", { name: "Open Timeline" }))
  await screen.findByText("125.00 USD · Money out")
  await page.screenshot({ path: "/tmp/loupe-timeline-payment.png" })
  fireEvent.click(screen.getByText("Supplier transfer"))
  await screen.findByRole("dialog", { name: "Transaction details" })
  expect(
    await within(
      screen.getByRole("dialog", { name: "Transaction details" })
    ).findByText(/Synthetic statement.pdf/)
  ).toBeTruthy()
  fireEvent.click(
    within(
      screen.getByRole("dialog", { name: "Transaction details" })
    ).getByRole("button", { name: "Close" })
  )
  fireEvent.click(screen.getByRole("button", { name: "Back to Financial" }))
  expect(
    (screen.getByLabelText("Search payments") as HTMLInputElement).value
  ).toBe("Supplier")
  expect(
    (
      screen.getByRole("checkbox", {
        name: /Select Supplier transfer on/,
      }) as HTMLInputElement
    ).checked
  ).toBe(true)
  fireEvent.click(screen.getByRole("button", { name: "Add to Timeline" }))
  fireEvent.click(
    screen.getByRole("button", { name: "Review Timeline entries" })
  )
  await screen.findByText(
    "0 ready · 1 already added · 1 without a payment date"
  )
  expect(screen.queryByRole("button", { name: "Add 1 to Timeline" })).toBeNull()
})
it.each(["Finding", "Observation"])(
  "adds a %s with an explicit event date, preserves its kind and opens its source entry",
  async (kind) => {
    await page.viewport(1280, 900)
    renderJourney("findings")
    const title = kind === "Finding" ? finding.title : observation.title
    const card = (await screen.findByRole("heading", { name: title })).closest(
      "article"
    )!
    fireEvent.click(
      within(card).getByRole("button", { name: "Add to Timeline" })
    )
    expect(
      (
        screen.getByRole("button", {
          name: "Review Timeline entries",
        }) as HTMLButtonElement
      ).disabled
    ).toBe(true)
    fireEvent.change(screen.getByLabelText("Event date", { exact: false }), {
      target: { value: "2021-02-09" },
    })
    fireEvent.click(
      screen.getByRole("button", { name: "Review Timeline entries" })
    )
    await screen.findByText(
      `2021-02-09 · ${kind} · Event date chosen by investigator`
    )
    await page.screenshot({
      path: `/tmp/loupe-timeline-${kind.toLowerCase()}-preview.png`,
    })
    fireEvent.click(screen.getByRole("button", { name: "Add 1 to Timeline" }))
    await screen.findByText("1 added to Timeline.")
    expect(calls[0].event_date).toBe("2021-02-09")
    fireEvent.click(screen.getByRole("button", { name: "Open Timeline" }))
    await screen.findByText(title)
    expect(screen.getAllByText(kind).length).toBeGreaterThan(0)
    fireEvent.click(screen.getByText(title))
    const original = await screen.findByRole("dialog", { name: title })
    expect(await within(original).findByText(finding.body)).toBeTruthy()
    fireEvent.click(within(original).getByRole("button", { name: "Close" }))
    fireEvent.click(screen.getByRole("button", { name: "Back to Financial" }))
    await screen.findByRole("heading", { name: "Findings & Observations" })
  }
)
it("keeps the preview usable on a small screen after a stale save, then retries", async () => {
  await page.viewport(420, 640)
  failSave = true
  render(
    <MemoryRouter>
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { mutations: { retry: false } } })
        }
      >
        <AddToTimelineDialog
          caseId="case"
          ids={["payment", "undated"]}
          onClose={() => {}}
        />
      </QueryClientProvider>
    </MemoryRouter>
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Review Timeline entries" })
  )
  fireEvent.click(
    await screen.findByRole("button", { name: "Add 1 to Timeline" })
  )
  await screen.findByRole("alert")
  expect(saved).toHaveLength(0)
  await page.screenshot({ path: "/tmp/loupe-timeline-retry-mobile.png" })
  expect(
    screen
      .getByRole("button", { name: "Refresh preview" })
      .getBoundingClientRect().bottom
  ).toBeLessThanOrEqual(640)
  fireEvent.click(screen.getByRole("button", { name: "Refresh preview" }))
  await waitFor(() => expect(screen.queryByRole("alert")).toBeNull())
  fireEvent.click(screen.getByRole("button", { name: "Add 1 to Timeline" }))
  await screen.findByText("1 added to Timeline.")
  expect(saved).toHaveLength(1)
})

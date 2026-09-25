import "@/styles/globals.css"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { page } from "vitest/browser"
import { fetchAPI } from "@/lib/api-client"
import { AddSavedStatementPayment } from "./AddSavedStatementPayment"
import { ImportedRecordsPanel } from "./ImportedRecordsPanel"
import {
  useFinancialDraftStore,
  financialDraftKey,
} from "../stores/financial-drafts"

vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(),
}))
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({ canEdit: true }),
}))
vi.mock("./PaymentCounterpartyPicker", () => ({
  PaymentCounterpartyPicker: () => null,
}))
vi.mock("./TransactionSourceHighlight", () => ({
  TransactionSourceHighlight: ({
    locatorPayload,
  }: {
    locatorPayload: { page: number }
  }) => <p>Synthetic original · page {locatorPayload.page}</p>,
}))

const caseId = "10000000-0000-4000-8000-000000000001"
const sourceId = "10000000-0000-4000-8000-000000000002"
const fileId = "10000000-0000-4000-8000-000000000003"
const anchor = { relation: "after", row_id: "printed:first" }
const details = {
  case_id: caseId,
  source_document_id: sourceId,
  evidence_file_id: fileId,
  revision: "a".repeat(64),
  currency: "USD",
  pages: [1, 2, 3],
  details: {
    holder: "Synthetic Company",
    account_number: "000123",
    institution: "Synthetic Bank",
  },
  requires_manual_position: true,
  source_position_rows: [
    {
      id: "printed:first",
      page_number: 1,
      kind: "transaction",
      fields: { date: "2026-01-01", description: "Earlier payment" },
    },
    {
      id: "printed:next",
      page_number: 3,
      kind: "transaction",
      fields: { date: "2026-01-03", description: "Later payment" },
    },
  ],
}
const initial = {
  id: "manual:synthetic",
  excluded: false,
  manual_page: 2,
  source_order_anchor: anchor,
  date: "2026-01-02",
  date_unprinted: false,
  date_values: {},
  description: "Payment missed on unread page",
  counterparty: "Synthetic payer",
  amount_minor: "500",
  direction: "credit",
  balance_minor: null,
  reason: "Checked source",
}
let savedRow: Record<string, unknown>
let client: QueryClient
const requests: { url: string; body: unknown }[] = []
beforeEach(async () => {
  await page.viewport(1440, 1000)
  savedRow = { ...initial }
  requests.length = 0
  useFinancialDraftStore.setState({ drafts: {} })
  client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  vi.mocked(fetchAPI).mockReset()
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (url.includes("/details?")) return details as never
    if (url.includes("/manual-payment?")) {
      requests.push({ url, body: options?.body })
      savedRow = {
        ...initial,
        ...(options?.body as { row: Record<string, unknown> }).row,
      }
      return {
        transaction_id: null,
        pending_reconciliation: true,
        blockers: [{ message: "The closing balance still needs comparison." }],
      } as never
    }
    if (url.includes("/complete-record?")) {
      requests.push({ url, body: options?.body })
      return {
        transaction_id: "saved-payment",
        pending_reconciliation: false,
        blockers: [],
      } as never
    }
    if (url.includes("/incomplete-records?"))
      return {
        records: [
          {
            id: savedRow.id,
            source_document_id: sourceId,
            evidence_file_id: fileId,
            filename: "Synthetic saved statement.pdf",
            currency: "USD",
            page_number: 2,
            locator: { kind: "page_only", page: 2 },
            original_text: "Investigator entry",
            missing_fields: [],
            version: 0,
            fields: savedRow,
          },
        ],
        total: 1,
      } as never
    throw Error(`Unexpected synthetic endpoint ${url}`)
  })
})
afterEach(() => {
  cleanup()
  client.clear()
  vi.clearAllMocks()
})
function records(onOpen = vi.fn()) {
  render(
    <QueryClientProvider client={client}>
      <ImportedRecordsPanel
        caseId={caseId}
        params={{ sourceDocumentId: sourceId }}
        onOpen={onOpen}
      />
    </QueryClientProvider>
  )
  return onOpen
}
async function openRecord() {
  fireEvent.click(await screen.findByText(/1 imported record has/))
  fireEvent.click(screen.getByRole("button", { name: "Open record" }))
  return await screen.findByLabelText(/^Printed position manual:/)
}

it("adds on an unread saved source page, retains the chosen boundary, then corrects the pending record without losing it", async () => {
  const onSaved = vi.fn()
  const mounted = render(
    <QueryClientProvider client={client}>
      <AddSavedStatementPayment
        caseId={caseId}
        sourceId={sourceId}
        onSaved={onSaved}
      />
    </QueryClientProvider>
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Add a missed transaction" })
  )
  await screen.findByLabelText("Missed payment PDF page")
  fireEvent.change(screen.getByLabelText("Missed payment PDF page"), {
    target: { value: "2" },
  })
  const position = screen.getByLabelText(/^Printed position manual:/)
  fireEvent.change(position, { target: { value: "after:printed:first" } })
  fireEvent.change(screen.getByLabelText("Missed payment date"), {
    target: { value: "2026-01-02" },
  })
  fireEvent.change(screen.getByLabelText("Description"), {
    target: { value: "Payment missed on unread page" },
  })
  fireEvent.change(screen.getByLabelText("Money in or out"), {
    target: { value: "credit" },
  })
  fireEvent.change(screen.getByLabelText("Amount (USD)"), {
    target: { value: "5.00" },
  })
  fireEvent.click(screen.getByRole("button", { name: "Close and keep draft" }))
  fireEvent.click(
    screen.getByRole("button", { name: "Add a missed transaction" })
  )
  expect(await screen.findByLabelText(/^Printed position manual:/)).toHaveValue(
    "after:printed:first"
  )
  expect(screen.getByText("Synthetic original · page 2")).toBeVisible()
  fireEvent.click(screen.getByRole("button", { name: "Save payment" }))
  await screen.findByText("The closing balance still needs comparison.")
  expect(onSaved).not.toHaveBeenCalled()
  expect(requests[0].body).toMatchObject({
    row: { manual_page: 2, source_order_anchor: anchor, amount_minor: "500" },
  })
  mounted.unmount()
  const onOpen = records()
  const retainedPosition = await openRecord()
  expect(retainedPosition).toHaveValue("after:printed:first")
  fireEvent.change(screen.getByLabelText("Description"), {
    target: { value: "Corrected saved description" },
  })
  fireEvent.click(screen.getByRole("button", { name: "Save correction" }))
  await waitFor(() => expect(onOpen).toHaveBeenCalledWith("saved-payment"))
  expect(requests[1].body).toMatchObject({
    version: 0,
    row: {
      manual_page: 2,
      source_order_anchor: anchor,
      description: "Corrected saved description",
    },
  })
})

it("preserves a saved anchor when reopening a browser draft created before placement support", async () => {
  const { source_order_anchor: _anchor, ...oldFields } = initial
  void _anchor
  useFinancialDraftStore
    .getState()
    .put(financialDraftKey(caseId, `incomplete:${sourceId}:${initial.id}:0`), {
      fields: { ...oldFields, description: "Unfinished older draft" },
      currency: "USD",
      amount: "",
      balance: "",
      changeBalance: false,
    })
  const onOpen = records()
  expect(await openRecord()).toHaveValue("after:printed:first")
  expect(screen.getByLabelText("Description")).toHaveValue(
    "Unfinished older draft"
  )
  fireEvent.click(screen.getByRole("button", { name: "Save correction" }))
  await waitFor(() => expect(onOpen).toHaveBeenCalledWith("saved-payment"))
  expect(requests[0].body).toMatchObject({
    row: { source_order_anchor: anchor, description: "Unfinished older draft" },
  })
})

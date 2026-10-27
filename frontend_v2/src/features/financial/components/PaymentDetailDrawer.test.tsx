import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { RowJudgements } from "../hooks/use-judgement-rows"
import type { Judgement } from "../lib/judgements"
import { LedgerSourceDialog } from "./LedgerSourceDialog"

vi.mock("../hooks/use-financial-finding-index", () => ({ useFinancialFindingIndex: () => ({ data: [] }) }))
vi.mock("../hooks/use-financial-access", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../hooks/use-financial-access")>()),
  useFinancialAccess: () => ({ canEdit: true, canUpload: true, ready: true, error: false }),
}))
vi.mock("./TransactionSourceHighlight", () => ({ TransactionSourceHighlight: () => <div data-testid="highlight" /> }))
vi.mock("./AccountOwnershipReview", () => ({ AccountOwnershipReview: () => <button>Review this account’s ownership</button> }))
vi.mock("./MoneyTrailReview", () => ({ MoneyTrailReview: () => <button>Link transfer or follow this payment</button> }))
vi.mock("./NearbyPaymentSearch", () => ({ NearbyPaymentSearch: () => <button>Related payments</button> }))
vi.mock("./TransactionNote", () => ({ TransactionNote: () => <button>Add investigation note</button> }))
vi.mock("./SourceCustodyPanel", () => ({ SourceCustodyPanel: () => <p>Source custody records</p> }))
vi.mock("./JudgementCalls", () => ({ RowJudgementMarkers: () => <button>Checked guess · Why?</button> }))
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

const field = (text: string) => ({ text, start: 0, end: text.length })
const party = (name: string) => ({
  party: { ...field(name), name, qualifier: null },
  bank: field("MONEX"),
  account: { ...field("112180000028366257"), kind: "clabe" },
})
const citation = {
  case_id: "case",
  transaction_id: "row",
  ref_id: "TX-P2M0-X5V3-S8XM",
  source_document_id: "doc",
  evidence_file_id: "11111111-1111-4111-8111-111111111111",
  filename: "07 ARRENDO MONEX MXN JUL 2025.pdf",
  sha256_at_ingestion: "a".repeat(64),
  recorded_digest_matches: true,
  file_bytes_verified: false,
  locator_state: "stored",
  locator: { kind: "page_only", page: 5 },
  ledger_status: "admitted",
  superseded_by_id: null,
  limitation: "Stored citation only.",
  transaction: {
    key: "row",
    case_id: "case",
    account_id: "acct",
    account_label: "Monex · 2836625 · ARRENDO SERV SA DE CV",
    source_document_id: "doc",
    ingestion_run_id: "run",
    statement_period_id: "period",
    ref_id: "TX-P2M0-X5V3-S8XM",
    row_index: 8,
    amount_minor: "1417500000",
    currency: "MXN",
    direction: "credit",
    running_balance_minor: "1062867",
    transaction_date: "2025-07-25",
    posted_date: null,
    value_date: null,
    effective_date: null,
    ordering_date: "2025-07-25",
    ordering_date_source: "transaction",
    description: "Nombre del Ordenante:ARRENDO SERV Concepto de Pago:TRASPASO CTAS PROPIAS",
    counterparty_raw: null,
    transaction_type: null,
    bank_reference: null,
    proof_class: "p3",
    extraction_layer: 4,
    ledger_status: "admitted",
    quarantine_reason: null,
    superseded_by_id: null,
    category: "Transfers",
    transfer_details: {
      method: "SPEI",
      layout: "kapital-delimited-spei",
      direction: "credit",
      sender: party("ARRENDO SERV"),
      recipient: party("ARRENDO SERV SA DE CV"),
      payment_references: [],
      ownership_established: false,
    },
  },
}

it("lays the payment out as header, judgement calls, who, category, source and linked, keeping every action", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(citation)))
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <RowJudgements.Provider value={{ caseId: "case", lookup: () => [{ id: "j1" } as Judgement] }}>
        <LedgerSourceDialog caseId="case" transactionId="row" onClose={vi.fn()} onAdjudicate={vi.fn()} inline />
      </RowJudgements.Provider>
    </QueryClientProvider>
  )
  const details = await screen.findByRole("region", { name: "Payment details" })
  // Header: direction, amount, date, account, status, how it was read.
  expect(within(details).getByText("Money in")).toBeTruthy()
  expect(within(details).getByText("14,175,000.00 MXN")).toBeTruthy()
  expect(within(details).getByText("2025-07-25")).toBeTruthy()
  expect(within(details).getByText(citation.transaction.account_label)).toBeTruthy()
  expect(within(details).getByText("Investigator reviewed")).toBeTruthy()
  // Judgement calls on this payment, with the way to all of them.
  const calls = within(details).getByRole("region", { name: "Judgement calls on this payment (1)" })
  expect(within(calls).getByRole("button", { name: "Checked guess · Why?" })).toBeTruthy()
  expect(within(calls).getByRole("link", { name: "See all judgement calls →" }).getAttribute("href")).toBe(
    "/cases/case/financial?view=statements&judgements=1"
  )
  // Who / Category / Source sections with what the row hides.
  expect(within(details).getByRole("region", { name: "Who" })).toBeTruthy()
  expect(within(within(details).getByRole("region", { name: "Category" })).getByText("Transfers")).toBeTruthy()
  const source = within(details).getByRole("region", { name: "Source" })
  expect(within(source).getByText("10,628.67 MXN")).toBeTruthy()
  expect(within(source).getByText("Not recorded")).toBeTruthy()
  expect(within(source).getByText("Page 5")).toBeTruthy()
  expect(within(source).getByText("TX-P2M0-X5V3-S8XM · 07 ARRENDO MONEX MXN JUL 2025.pdf")).toBeTruthy()
  // Printed transfer details: one click on a labelled button.
  const transfer = within(source).getByRole("button", { name: /Sender, recipient and account details/ })
  expect(transfer.getAttribute("aria-expanded")).toBe("false")
  fireEvent.click(transfer)
  expect(transfer.getAttribute("aria-expanded")).toBe("true")
  expect(within(source).getByText("Recipient: ARRENDO SERV SA DE CV")).toBeVisible()
  // Every action stays one click away.
  const actions = within(details).getByRole("group", { name: "Change this payment" })
  for (const name of ["Edit names and category", "Create finding", "Correct a value", "Exclude from totals"])
    expect(within(actions).getByRole("button", { name })).toBeTruthy()
  const linked = within(details).getByRole("region", { name: "Linked" })
  expect(within(linked).getByRole("button", { name: "Link transfer or follow this payment" })).toBeTruthy()
  expect(within(linked).getByRole("button", { name: "Related payments" })).toBeTruthy()
  expect(screen.getByRole("button", { name: "Review this account’s ownership" })).toBeTruthy()
  expect(screen.getByRole("button", { name: "Add investigation note" })).toBeTruthy()
  fireEvent.click(screen.getByRole("button", { name: "File history and technical details" }))
  expect(screen.getByText("Source custody records")).toBeVisible()
})

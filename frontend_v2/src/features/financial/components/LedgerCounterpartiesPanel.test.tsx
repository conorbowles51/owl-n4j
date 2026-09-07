import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, fireEvent } from "@testing-library/react"
import { it, expect, vi, afterEach } from "vitest"
import { LedgerCounterpartiesPanel } from "./LedgerCounterpartiesPanel"
vi.mock("./LedgerSourceDialog", () => ({
  LedgerSourceDialog: ({
    caseId,
    transactionId,
  }: {
    caseId: string
    transactionId: string
  }) => (
    <p>
      Source {caseId}/{transactionId}
    </p>
  ),
}))
afterEach(() => vi.restoreAllMocks())
const totals = {
  currency: "GBP",
  rows: 1,
  credits_minor: "9007199254740993",
  debits_minor: "0",
  net_minor: "9007199254740993",
}
const answer = {
  case_id: "case-a",
  account_id: null,
  start_date: null,
  end_date: null,
  label_basis: "counterparty_raw_exact",
  counterparty_limitation: "No identity or transfer matching.",
  available: true,
  reason: null,
  applied: false,
  limitation: "Not complete evidence.",
  included_rows: 1,
  excluded_rows: 0,
  currencies: [totals],
  counterparties: [
    {
      ...totals,
      label: "Source label",
      transaction_ids: ["tx-a"],
      source_document_ids: ["doc-a"],
    },
  ],
}
function mount(data: unknown = answer) {
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async () => new Response(JSON.stringify(data)))
  const client = new QueryClient()
  const element = (caseId = "case-a") => (
    <QueryClientProvider client={client}>
      <LedgerCounterpartiesPanel caseId={caseId} params={{}} />
    </QueryClientProvider>
  )
  const view = render(element())
  return { fetch, client, change: () => view.rerender(element("case-b")) }
}
it("loads exact counterparty totals on request and opens only a contributing source", async () => {
  const { fetch, change } = mount()
  expect(fetch).not.toHaveBeenCalled()
  fireEvent.click(
    screen.getByRole("button", { name: "Read ledger counterparty totals" })
  )
  expect(
    await screen.findByText(/Credits: 90071992547409.93 GBP/)
  ).toBeInTheDocument()
  fireEvent.click(screen.getByText("Contributing readings (1)"))
  fireEvent.click(
    screen.getByRole("button", {
      name: "Open contributing reading 1",
    })
  )
  expect(screen.getByText("Source case-a/tx-a")).toBeInTheDocument()
  change()
  expect(screen.queryByText("Source case-a/tx-a")).not.toBeInTheDocument()
  expect(screen.queryByText(/Credits:/)).not.toBeInTheDocument()
})
it.each([
  { case_id: "other" },
  { start_date: "2026-01-01" },
  { account_id: "other" },
  { label_basis: "inferred" },
  { counterparties: [{ ...answer.counterparties[0], credits_minor: "1" }] },
  {
    counterparties: [
      { ...answer.counterparties[0], transaction_ids: ["tx-a", "tx-a"] },
    ],
  },
  { currencies: [{ ...totals, credits_minor: "4" }] },
])("refuses mismatched counterparty totals %j", async (change) => {
  mount({ ...answer, ...change })
  fireEvent.click(
    screen.getByRole("button", { name: "Read ledger counterparty totals" })
  )
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Counterparty totals unavailable"
  )
  expect(screen.queryByText(/Credits:/)).not.toBeInTheDocument()
})
it("keeps unknown separate from empty activity", async () => {
  mount({
    ...answer,
    available: false,
    reason: "Too many rows.",
    included_rows: null,
    excluded_rows: null,
    currencies: [],
    counterparties: [],
  })
  fireEvent.click(
    screen.getByRole("button", { name: "Read ledger counterparty totals" })
  )
  expect(
    await screen.findByText("Counterparty totals unavailable. Too many rows.")
  ).toBeInTheDocument()
  expect(screen.queryByText(/No eligible postings/)).not.toBeInTheDocument()
})

it.each([
  [null, "Counterparty not recorded"],
  ["", "Blank source label"],
  ["Acme ", '"Acme "'],
])("preserves label meaning %s", async (label, expected) => {
  mount({ ...answer, counterparties: [{ ...answer.counterparties[0], label }] })
  fireEvent.click(
    screen.getByRole("button", { name: "Read ledger counterparty totals" })
  )
  expect(
    await screen.findByText(new RegExp(String(expected)))
  ).toBeInTheDocument()
})

it("pages label groups without changing their reconciled total", async () => {
  const group = {...totals, credits_minor:"1", debits_minor:"0", net_minor:"1"}
  mount({...answer, included_rows:26, currencies:[{...group, rows:26, credits_minor:"26", net_minor:"26"}],
    counterparties:Array.from({length:26},(_,index)=>({...group,label:`Label ${index}`,transaction_ids:[`tx-${index}`],source_document_ids:[`doc-${index}`]}))})
  fireEvent.click(screen.getByRole("button",{name:"Read ledger counterparty totals"}))
  expect(await screen.findByText(/"Label 0"/)).toBeInTheDocument()
  expect(screen.queryByText(/"Label 25"/)).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole("button",{name:"Next counterparty totals"}))
  expect(screen.getByText(/"Label 25"/)).toBeInTheDocument()
  expect(screen.queryByText(/"Label 0"/)).not.toBeInTheDocument()
})
it("refreshes after a ledger decision invalidates the shared cache", async () => {
  const {fetch,client}=mount()
  fireEvent.click(screen.getByRole("button",{name:"Read ledger counterparty totals"}))
  await screen.findByText(/Credits:/)
  fetch.mockImplementation(async()=>new Response(JSON.stringify({...answer,included_rows:0,excluded_rows:1,currencies:[],counterparties:[]})))
  await client.invalidateQueries({queryKey:["financial-ledger","case-a"]})
  expect(await screen.findByText(/No eligible postings/)).toBeInTheDocument()
  expect(screen.queryByText(/Credits:/)).not.toBeInTheDocument()
})

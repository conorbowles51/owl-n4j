import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import type { LedgerTransaction } from "../api"
import { paymentFixture } from "../lib/payment-fixture.test-support"
import { unconfirmedNamesLabel } from "../lib/payment-naming"
import { BulkConfirmReadings } from "./BulkConfirmReadings"

vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
vi.mock("@/features/auth/hooks/use-auth", () => ({
  useAuthStore: (pick: (state: { user: { name: string; username: string } }) => unknown) =>
    pick({ user: { name: "Alex Rivera", username: "alex" } }),
}))

const origin = { kind: "model" as const, model: "Claude", for: { name: "Neil" }, at: "2026-11-08T10:00:00+00:00" }
const read = { source: "model_reading" as const, label: "Read by Claude · not confirmed", origin }
function row(key: string, extra: Partial<LedgerTransaction> = {}): LedgerTransaction {
  return {
    ...paymentFixture, key, case_id: "case", direction: "debit", from_name: "HOLDER", to_name: `PAYEE ${key}`, label_version: 1,
    label_sources: { from_name: { source: "account" }, to_name: read }, ...extra,
  } as LedgerTransaction
}
const KEY = ["financial-ledger", "case", null]

beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(fetchAPI).mockImplementation(async (_url, options) => ({
    case_id: "case", confirmed: (options?.body as { transactions: unknown[] }).transactions.length, skipped: 0,
  }))
})

function mount(rows: LedgerTransaction[], notLoaded = 0) {
  const client = new QueryClient()
  client.setQueryData(KEY, { transactions: rows, total: rows.length })
  render(
    <QueryClientProvider client={client}>
      <BulkConfirmReadings caseId="case" rows={rows} notLoaded={notLoaded} />
    </QueryClientProvider>
  )
  return client
}

it("confirms every selected reading in one call after saying how many and that there is no undo", async () => {
  const named = row("n", { label_sources: { from_name: { source: "account" }, to_name: { source: "investigator" } } })
  const client = mount([row("a"), row("b"), named])
  fireEvent.click(screen.getByRole("button", { name: "Confirm selected (2)" }))
  expect(screen.getByRole("status").textContent).toMatch(/2 selected payments\? Each is saved as confirmed by Alex Rivera today/)
  expect(screen.getByRole("status").textContent).toMatch(/no undo/)
  expect(fetchAPI).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole("button", { name: "Confirm 2" }))
  await waitFor(() => expect(fetchAPI).toHaveBeenCalledTimes(1))
  expect(vi.mocked(fetchAPI).mock.calls[0][1]).toMatchObject({
    method: "POST",
    body: { transactions: [{ id: "a", version: 1 }, { id: "b", version: 1 }], fields: ["from_name", "to_name"] },
  })
  await waitFor(() => {
    const rows = (client.getQueryData(KEY) as { transactions: LedgerTransaction[] }).transactions
    expect(rows.slice(0, 2).map((item) => item.label_sources?.to_name?.source)).toEqual(["investigator", "investigator"])
    expect(rows[0].label_sources?.to_name?.explanation).toMatch(/^Confirmed by Alex Rivera/)
  })
})

it("Cancel saves nothing, and selected payments not loaded are named, not dropped silently", () => {
  mount([row("a")], 3)
  expect(screen.getByText(/3 selected payments are not loaded in this view and are not included/)).toBeTruthy()
  fireEvent.click(screen.getByRole("button", { name: "Confirm selected (1)" }))
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }))
  expect(fetchAPI).not.toHaveBeenCalled()
})

it("the count says which kind of name it counts", () => {
  const holderRead = row("h", { label_sources: { from_name: read, to_name: { source: "investigator" } } })
  expect(unconfirmedNamesLabel(3, [row("a"), row("b"), holderRead])).toBe(
    "2 counterparty names and 1 account holder name in view read by Claude and not confirmed by a person"
  )
  expect(unconfirmedNamesLabel(1, [row("a")])).toBe("1 counterparty name in view read by Claude and not confirmed by a person")
  expect(unconfirmedNamesLabel(40, null)).toBe(
    "40 names (counterparty or account holder) in view read by Claude and not confirmed by a person"
  )
})

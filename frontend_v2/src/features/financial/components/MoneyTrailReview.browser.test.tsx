import "@/styles/globals.css"
import { page } from "vitest/browser"
import { MemoryRouter } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { financialAPI } from "../api"
import { MoneyTrailReview } from "./MoneyTrailReview"
import { ReviewedMoneyTrails } from "./ReviewedMoneyTrails"
import type { LedgerTransaction } from "../api"
import { useFinancialDraftStore } from "../stores/financial-drafts"
import {
  internalActivity,
  savedTrail,
  trailNarrative,
  type SavedTrail,
} from "../lib/money-trails"

vi.mock("@/lib/api-client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(),
}))
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({ canEdit: true, ready: true }),
}))
const uuid = (n: number) =>
  `10000000-0000-4000-8000-${String(n).padStart(12, "0")}`
const caseId = uuid(1),
  debit = uuid(2),
  credit = uuid(3),
  supplier = uuid(4)
const payments = [
  {
    key: debit,
    account_id: uuid(5),
    direction: "debit",
    description: "Transfer to Bank B",
    ref_id: "TX-SEND",
  },
  {
    key: credit,
    account_id: uuid(6),
    direction: "credit",
    description: "Transfer from Bank A",
    ref_id: "TX-RECEIVE",
  },
  {
    key: supplier,
    account_id: uuid(6),
    direction: "debit",
    description: "Water supplier",
    ref_id: "TX-WATER",
  },
].map((p, i) => ({
  ...p,
  case_id: caseId,
  source_document_id: uuid(i + 10),
  currency: "USD",
  amount_minor: "500000",
  account_type: "bank",
  account_label:
    i === 0 ? "Example business · Bank A" : "Example business · Bank B",
  ordering_date: "2025-10-17",
  running_balance_minor: null,
  superseded_by_id: null,
}))
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  useFinancialDraftStore.setState({ drafts: {} })
})

it("reviews a transfer, follows the receipt to a supplier, persists both links and keeps internal accounting distinct", async () => {
  let records: SavedTrail[] = []
  vi.spyOn(financialAPI, "getLedgerTransactions").mockResolvedValue({
    case_id: caseId,
    total: 3,
    transactions: payments,
  } as never)
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (String(url).startsWith("/api/timeline/entries")) {
      const body = options?.body as {
        source_kind: string
        source_ids: string[]
      }
      expect(body.source_kind).toBe("money_trail")
      expect(body.source_ids).toEqual([records[0].id])
      if (String(url).includes("preview"))
        return {
          case_id: caseId,
          revision: "b".repeat(64),
          ready: 1,
          already_added: 0,
          undated: 0,
          rows: [
            {
              source_id: records[0].id,
              name: "Example business · Bank A → Bank B",
              status: "ready",
              event: {
                key: "transfer-1",
                date: "2025-10-17",
                type: "Transfer",
                amount: "5000.00 USD",
                source: {
                  label: "Both original statements",
                  date_basis: "Sending entry",
                },
              },
            },
          ],
        } as never
      return {
        case_id: caseId,
        added: 1,
        already_added: 0,
        undated: 0,
        event_keys: ["transfer-1"],
      } as never
    }
    if (options?.method !== "POST")
      return { case_id: caseId, trails: records } as never
    const body = options.body as Record<string, unknown>
    const input = { payments: [], allow_fx: false, ...body }
    const details = {
      case_id: caseId,
      kind: body.kind,
      input,
      payments:
        body.kind === "transfer" ? payments.slice(0, 2) : payments.slice(1),
      ownership: {},
      common_holders:
        body.kind === "transfer"
          ? [{ id: uuid(20), name: "Example business" }]
          : [],
      internal_transfer: body.kind === "transfer",
      implied_exchange_rate: null,
      receipt_unallocated_minor: body.kind === "transfer" ? null : "100000",
      warnings: [
        "Same-day order is not established. An allocation is an investigator interpretation.",
      ],
      source_revision: "a".repeat(64),
    }
    if (String(url).includes("preview")) return details as never
    const record = savedTrail.parse({
      id: body.id,
      case_id: caseId,
      kind: body.kind,
      revision: 1,
      active: true,
      status: "current",
      details,
      history: [{ reason: body.reason }],
    })
    records = [...records, record]
    return record as never
  })
  await page.viewport(1280, 900)
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const mount = () =>
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <MoneyTrailReview caseId={caseId} transactionIds={[debit, credit]} />
        </MemoryRouter>
      </QueryClientProvider>
    )
  mount()
  await page
    .getByRole("button", { name: "Review saved transfers and money trails" })
    .click()
  await screen.findByLabelText("Sending account’s debit")
  fireEvent.click(
    screen.getByRole("button", { name: "Use selected transactions (2)" })
  )
  fireEvent.change(screen.getByLabelText("Reason and supporting evidence"), {
    target: { value: "Both bank sources reviewed; common holder confirmed." },
  })
  await page.getByRole("button", { name: "Preview link" }).click()
  expect(await screen.findByLabelText("Money trail preview")).toHaveTextContent(
    "reviewed common holder"
  )
  await page.getByRole("button", { name: "Save reviewed link" }).click()
  const receipt = await screen.findByRole("status")
  await waitFor(() => expect(receipt).toHaveTextContent("Saved to this case"))
  expect(records).toHaveLength(1)
  fireEvent.click(
    within(receipt).getByRole("button", { name: "Add transfer to Timeline" })
  )
  await page.getByRole("button", { name: "Review Timeline entries" }).click()
  expect(await screen.findByText("Both original statements")).toBeVisible()
  await page.getByRole("button", { name: "Add 1 to Timeline" }).click()
  expect(await screen.findByText("1 added to Timeline.")).toBeVisible()
  await page.getByRole("button", { name: "Done", exact: true }).click()
  expect(internalActivity(payments, records).ids).toEqual(
    new Set([debit, credit])
  )
  expect([...internalActivity(payments, records).movements.values()]).toEqual([
    500000n,
  ])
  expect(internalActivity(payments.slice(1), records).ids.size).toBe(0)
  expect(
    internalActivity(payments, [{ ...records[0], status: "source_changed" }])
      .ids.size
  ).toBe(0)
  fireEvent.click(
    within(receipt).getByRole("button", { name: "Follow this receipt" })
  )
  fireEvent.click(screen.getByRole("checkbox", { name: /Water supplier/ }))
  fireEvent.change(screen.getByLabelText("Allocation for TX-WATER"), {
    target: { value: "4000.00" },
  })
  fireEvent.change(screen.getByLabelText("Reason and supporting evidence"), {
    target: {
      value: "Manual allocation of part of the receipt; other funds may exist.",
    },
  })
  await page.getByRole("button", { name: "Preview link" }).click()
  expect(await screen.findByLabelText("Money trail preview")).toHaveTextContent(
    "1000.00 USD"
  )
  await page.getByRole("button", { name: "Save reviewed link" }).click()
  await waitFor(() => expect(records).toHaveLength(2))
  expect(records[1].details.input.payments).toEqual([
    { transaction_id: supplier, amount_minor: "400000" },
  ])
  expect(trailNarrative(records[1])).toContain("5000.00 USD")
  cleanup()
  mount()
  await page.viewport(390, 844)
  await page
    .getByRole("button", { name: "Review saved transfers and money trails" })
    .click()
  expect(await screen.findByLabelText("Relationship")).toHaveValue("allocation")
  const saved = screen.getByLabelText("Saved money trails")
  expect(saved).toHaveTextContent("Internal transfer — reviewed common holder")
  expect(saved).toHaveTextContent("Onward allocation")
  expect(
    screen.getByRole("dialog").getBoundingClientRect().width
  ).toBeLessThanOrEqual(390)
  await page.screenshot({ path: "/tmp/loupe-money-trail-mobile.png" })
  cleanup()
  await page.viewport(1280, 900)
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ReviewedMoneyTrails
          caseId={caseId}
          rows={payments as unknown as LedgerTransaction[]}
        />
      </MemoryRouter>
    </QueryClientProvider>
  )
  expect(
    await screen.findByLabelText("Reviewed money trails")
  ).toHaveTextContent("Example business · Bank A")
  expect(screen.getByLabelText("Reviewed money trails")).toHaveTextContent(
    "4000.00 USD allocated to Water supplier"
  )
  await page
    .getByRole("button", { name: "Open transfer and statements" })
    .click()
  expect(await screen.findByLabelText("Relationship")).toHaveValue("transfer")
})

it("reviews split principal and fees, reopens the same amounts, and keeps fee/residual spending outside internal totals", async () => {
  await page.viewport(900, 900)
  const rows = [
    { ...payments[0], amount_minor: "501000" },
    { ...payments[1], amount_minor: "300000" },
    {
      ...payments[1],
      key: uuid(31),
      ref_id: "TX-RECEIVE-2",
      amount_minor: "200000",
    },
    { ...payments[2] },
  ]
  let record: SavedTrail | null = null
  vi.spyOn(financialAPI, "getLedgerTransactions").mockResolvedValue({
    case_id: caseId,
    total: rows.length,
    transactions: rows,
  } as never)
  vi.mocked(fetchAPI).mockImplementation(async (_url, options) => {
    if (options?.method !== "POST")
      return { case_id: caseId, trails: record ? [record] : [] }
    const input = options.body as {
      id: string
      kind: string
      reason: string
      transfer_parts: {
        transaction_id: string
        principal_minor: string
        fee_minor: string
      }[]
    }
    expect(input.transfer_parts).toEqual([
      { transaction_id: debit, principal_minor: "500000", fee_minor: "1000" },
      { transaction_id: credit, principal_minor: "300000", fee_minor: "0" },
      { transaction_id: uuid(31), principal_minor: "200000", fee_minor: "0" },
    ])
    const details = {
      case_id: caseId,
      kind: "transfer",
      input,
      payments: rows.slice(0, 3),
      ownership: {},
      common_holders: [{ id: uuid(20), name: "Example business" }],
      internal_transfer: true,
      implied_exchange_rate: null,
      receipt_unallocated_minor: null,
      warnings: ["Fees remain external spending."],
      source_revision: "a".repeat(64),
      transfer_breakdown: {
        sent_currency: "USD",
        sent_minor: "500000",
        received_currency: "USD",
        received_minor: "500000",
        fees: [{ currency: "USD", amount_minor: "1000" }],
        entries: input.transfer_parts.map((part) => ({
          ...part,
          original_minor: rows.find((p) => p.key === part.transaction_id)!
            .amount_minor,
          direction: rows.find((p) => p.key === part.transaction_id)!.direction,
          currency: "USD",
          unassigned_minor: "0",
          remaining_after_other_links_minor: "0",
        })),
      },
    }
    if (_url.includes("preview")) return details
    record = savedTrail.parse({
      id: input.id,
      case_id: caseId,
      kind: "transfer",
      active: true,
      revision: 1,
      status: "current",
      details,
      history: [],
    })
    return record
  })
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const mount = () =>
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <MoneyTrailReview caseId={caseId} initialOpen />
        </MemoryRouter>
      </QueryClientProvider>
    )
  mount()
  fireEvent.click(
    await screen.findByLabelText(
      "This transfer has fees, split entries or only uses part of a payment"
    )
  )
  for (const name of ["TX-SEND", "TX-RECEIVE", "TX-RECEIVE-2"])
    fireEvent.click(screen.getByLabelText(`Include ${name} in transfer`))
  fireEvent.change(screen.getByLabelText("Principal for TX-SEND"), {
    target: { value: "5000" },
  })
  fireEvent.change(screen.getByLabelText("Fee for TX-SEND"), {
    target: { value: "10" },
  })
  fireEvent.change(screen.getByLabelText("Reason and supporting evidence"), {
    target: {
      value:
        "One debit sends 5,000 in two receipts. The printed 10 fee is separate from principal.",
    },
  })
  fireEvent.click(screen.getByRole("button", { name: "Preview link" }))
  const preview = await screen.findByLabelText("Money trail preview")
  expect(preview).toHaveTextContent("Fees: 10.00 USD")
  expect(preview).toHaveTextContent("TX-RECEIVE-2")
  fireEvent.click(
    within(preview).getByRole("button", { name: "Save reviewed link" })
  )
  await waitFor(() => expect(record).not.toBeNull())
  const internal = internalActivity(rows, [record!])
  expect([...internal.movements.values()]).toEqual([500000n])
  expect(internal.portions.get(debit)).toBe(500000n)
  expect(BigInt(rows[0].amount_minor) - internal.portions.get(debit)!).toBe(
    1000n
  )
  expect(internalActivity(rows.slice(1), [record!]).ids.size).toBe(0)
  expect(trailNarrative(record!)).toContain("fee 10.00 USD")
  cleanup()
  mount()
  const saved = await screen.findByLabelText("Saved money trails")
  fireEvent.click(
    within(saved).getByRole("button", { name: "Review or edit link" })
  )
  expect(screen.getByLabelText("Fee for TX-SEND")).toHaveValue("10.00")
  expect(screen.getByLabelText("Principal for TX-RECEIVE-2")).toHaveValue(
    "2000.00"
  )
  expect(
    within(saved).getAllByRole("button", { name: /Follow this receipt/ })
  ).toHaveLength(2)
  await page.viewport(390, 844)
  await page.screenshot({ path: "/tmp/loupe-split-transfer-mobile.png" })
  expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(390)
  client.clear()
})

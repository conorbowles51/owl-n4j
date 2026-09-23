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
    .getByRole("button", { name: "Open transfer and both statements" })
    .click()
  expect(await screen.findByLabelText("Relationship")).toHaveValue("transfer")
})

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { StatementCompareView, type CompareSide } from "./StatementCompareView"
import { pageRange } from "../lib/statement-compare"

vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(),
}))
vi.mock("@/components/ui/evidence-pdf-document", () => ({
  EvidencePdfDocument: ({
    evidenceId,
    page,
    onPageCount,
  }: {
    evidenceId: string
    page: number
    onPageCount: (id: string, count: number) => void
  }) => (
    <button onClick={() => onPageCount(evidenceId, 10)}>
      {evidenceId} page {page}
    </button>
  ),
}))

const caseId = "case-1"
const own: CompareSide = {
  fileId: "held-file",
  filename: "STATEMENTS 5630.pdf",
  startPage: 5,
  pages: [5, 6, 7, 8],
  status: "Held as possible duplicate",
  facts: {
    institution: "Truist Bank",
    account_number: "1000270585630",
    holder: "BEE THRIFTY CAMP SPRINGS LLC",
    period_start: "2023-12-01",
    period_end: "2023-12-29",
    currency: "USD",
    opening_balance_minor: "7865224",
    closing_balance_minor: "5694280",
    money_in_minor: "1250000",
    money_out_minor: "3420944",
    payment_count: 41,
  },
}
const other = {
  file_id: "original-file",
  source_document_id: "source-1",
  filename: "Dec 2023 (5630) (2).pdf",
  page_number: 1,
  status: "imported" as const,
  period_start: "2023-12-01",
  period_end: "2023-12-29",
  matching_statement: true,
}
const stored = {
  case_id: caseId,
  source_document_id: "source-1",
  evidence_file_id: "original-file",
  filename: "Dec 2023 (5630) (2).pdf",
  institution: "TRUIST BANK",
  account_number: "1000 2705 85630",
  holder: "Bee Thrifty Camp Springs LLC",
  period_start: "2023-12-01",
  period_end: "2023-12-29",
  currency: "USD",
  balance_convention: "asset_balance",
  pages: [1, 2, 3, 4],
  opening_balance_minor: "7865224",
  closing_balance_minor: "5694280",
  payment_count: 40,
  money_in_minor: "1250000",
  money_out_minor: "3420944",
  held_from_ledger: 0,
  mixed_currency: false,
}
let client: QueryClient

beforeEach(() => {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  vi.mocked(fetchAPI).mockReset()
  vi.mocked(fetchAPI).mockResolvedValue(stored as never)
})
afterEach(() => {
  cleanup()
  client.clear()
})

function mount(props: Partial<Parameters<typeof StatementCompareView>[0]> = {}) {
  const onOpenChange = vi.fn()
  render(
    <QueryClientProvider client={client}>
      <StatementCompareView
        caseId={caseId}
        own={own}
        other={other}
        open
        onOpenChange={onOpenChange}
        {...props}
      />
    </QueryClientProvider>
  )
  return onOpenChange
}

it("shows both statements side by side, each from its own first page and labelled", async () => {
  mount()
  const mine = screen.getByRole("region", { name: "This statement" })
  const theirs = screen.getByRole("region", { name: "Matching statement" })
  expect(within(mine).getByText("STATEMENTS 5630.pdf")).toBeVisible()
  expect(within(mine).getByText("2023-12-01 to 2023-12-29 · Pages 5 to 8 · Held as possible duplicate")).toBeVisible()
  expect(within(mine).getByRole("button", { name: "held-file page 5" })).toBeVisible()
  expect(await within(theirs).findByText("2023-12-01 to 2023-12-29 · Pages 1 to 4 · Already imported")).toBeVisible()
  expect(within(theirs).getByText("Dec 2023 (5630) (2).pdf")).toBeVisible()
  expect(within(theirs).getByRole("button", { name: "original-file page 1" })).toBeVisible()
  expect(fetchAPI).toHaveBeenCalledWith(
    "/api/financial/statement-import/sources/source-1/compare-facts?case_id=case-1"
  )
})

it("pages each side on its own", async () => {
  mount()
  const mine = screen.getByRole("region", { name: "This statement" })
  const theirs = screen.getByRole("region", { name: "Matching statement" })
  await within(theirs).findByText(/Pages 1 to 4/)
  fireEvent.click(within(mine).getByRole("button", { name: "Next page of this statement" }))
  expect(within(mine).getByRole("button", { name: "held-file page 6" })).toBeVisible()
  expect(within(theirs).getByRole("button", { name: "original-file page 1" })).toBeVisible()
  fireEvent.click(within(mine).getByRole("button", { name: "Back to page 5" }))
  expect(within(mine).getByRole("button", { name: "held-file page 5" })).toBeVisible()
})

it("names each fact for both statements and whether it agrees, with exact amounts", async () => {
  mount()
  const strip = screen.getByRole("region", { name: "Compared facts" })
  expect(await within(strip).findByText("1 of 10 facts differ.")).toBeVisible()
  const row = (label: string) => within(strip).getByRole("row", { name: new RegExp(`^${label}`) })
  expect(row("Account")).toHaveAttribute("data-result", "agrees")
  expect(row("Holder")).toHaveAttribute("data-result", "agrees")
  expect(row("Bank")).toHaveAttribute("data-result", "agrees")
  expect(row("Period")).toHaveAttribute("data-result", "agrees")
  expect(within(row("Opening balance")).getAllByText("78,652.24 USD")).toHaveLength(2)
  expect(within(row("Closing balance")).getAllByText("56,942.80 USD")).toHaveLength(2)
  expect(row("Closing balance")).toHaveAttribute("data-result", "agrees")
  expect(row("Money out")).toHaveAttribute("data-result", "agrees")
  expect(row("Number of payments")).toHaveAttribute("data-result", "differs")
  expect(within(row("Number of payments")).getByText("Differs")).toBeVisible()
  expect(within(row("Number of payments")).getByText("41")).toBeVisible()
  expect(within(row("Number of payments")).getByText("40")).toBeVisible()
})

it("says a value is not known instead of calling it equal", async () => {
  mount({ own: { ...own, facts: { ...own.facts!, opening_balance_minor: null, money_in_minor: null, notes: ["Some payments have no amount."] } } })
  const strip = screen.getByRole("region", { name: "Compared facts" })
  await within(strip).findByText(/facts differ|cannot be compared/)
  const opening = within(strip).getByRole("row", { name: /^Opening balance/ })
  expect(opening).toHaveAttribute("data-result", "unknown")
  expect(within(opening).getByText("Not known")).toBeVisible()
  expect(within(strip).getByText("This statement: Some payments have no amount.")).toBeVisible()
})

it("names payments held out of the ledger rather than counting them", async () => {
  vi.mocked(fetchAPI).mockResolvedValue({ ...stored, held_from_ledger: 2 } as never)
  mount()
  expect(
    await screen.findByText("Matching statement: 2 more payments are held out of the ledger and are not counted here.")
  ).toBeVisible()
})

it("does not invent figures for a matching statement that is not imported", () => {
  mount({ other: { ...other, status: "awaiting_import", source_document_id: null, page_number: 3 } })
  expect(fetchAPI).not.toHaveBeenCalled()
  expect(screen.getByText(/not imported yet, so its stored figures are not available/)).toBeVisible()
  const theirs = screen.getByRole("region", { name: "Matching statement" })
  expect(within(theirs).getByRole("button", { name: "original-file page 3" })).toBeVisible()
  expect(within(theirs).getByText(/Awaiting import/)).toBeVisible()
})

it("offers the decision inside the view and stays open after deciding", async () => {
  const decide = vi.fn()
  const onOpenChange = mount({
    decision: <button onClick={decide}>Don’t import this duplicate</button>,
  })
  const area = screen.getByRole("region", { name: "Decision in the comparison" })
  fireEvent.click(within(area).getByRole("button", { name: "Don’t import this duplicate" }))
  expect(decide).toHaveBeenCalledOnce()
  expect(onOpenChange).not.toHaveBeenCalled()
  expect(screen.getByRole("dialog", { name: "Compare side by side" })).toBeVisible()
  fireEvent.click(screen.getByRole("button", { name: "Close comparison" }))
  expect(onOpenChange).toHaveBeenCalledWith(false)
})

it("switches between the two documents on a narrow screen", () => {
  mount()
  const mine = screen.getByRole("region", { name: "This statement" })
  const theirs = screen.getByRole("region", { name: "Matching statement" })
  expect(mine.className).toContain("flex")
  expect(theirs.className).toContain("hidden md:flex")
  fireEvent.click(screen.getByRole("button", { name: "Matching statement" }))
  expect(screen.getByRole("button", { name: "Matching statement" })).toHaveAttribute("aria-pressed", "true")
  expect(screen.getByRole("region", { name: "This statement" }).className).toContain("hidden md:flex")
})

it("states page ranges plainly", () => {
  expect(pageRange([7, 5, 6], 5)).toBe("Pages 5 to 7")
  expect(pageRange([1], 1)).toBe("Page 1")
  expect(pageRange([], 3)).toBe("From page 3")
})

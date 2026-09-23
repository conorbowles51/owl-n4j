import "@/styles/globals.css"
import { page } from "vitest/browser"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { useFinancialDraftStore } from "../stores/financial-drafts"
import { SavedStatementRecovery } from "./SavedStatementRecovery"

vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
vi.mock("./TransactionSourceHighlight", () => ({
  TransactionSourceHighlight: () => (
    <div className="bg-white text-slate-900 p-5 border min-h-[300px]">
      <h2>Original synthetic PDF</h2>
      <p>Bank One · Account EUR-A · EUR</p>
      <p>Bank Two · Account USD-B · USD</p>
    </div>
  ),
}))
vi.mock("./LedgerPanel", () => ({
  LedgerPanel: ({ params }: { params: { sourceDocumentId: string } }) => (
    <p>Saved payments for {params.sourceDocumentId}</p>
  ),
}))
const input = {
  case_id: "case",
  source_document_id: "source",
  evidence_file_id: "file",
  recovery_revision: "a".repeat(64),
  currency: "EUR",
  pages: [1, 2],
  details: {
    holder: "Example business",
    account_number: "EUR-A",
    institution: "Bank One",
    period_start: "2026-05-01",
    period_end: "2026-05-31",
  },
  transactions: [
    {
      key: "one",
      description: "EUR supplier",
      ordering_date: "2026-05-03",
      amount_minor: "40000",
      currency: "EUR",
      direction: "debit",
      page: 1,
    },
    {
      key: "two",
      description: "USD transfer",
      ordering_date: "2026-05-04",
      amount_minor: "50000",
      currency: "EUR",
      direction: "credit",
      page: 2,
    },
  ],
  incomplete_records: [],
}
afterEach(() => {
  cleanup()
  useFinancialDraftStore.setState({ drafts: {} })
  vi.resetAllMocks()
})

it("keeps a recovery draft, previews each currency, saves once and reopens the corrected section", async () => {
  let saves = 0
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (String(url).endsWith("/recovery?case_id=case")) return input as never
    if (String(url).includes("/recovery/preview")) {
      const body = options?.body as {
        sections: { transaction_ids: string[]; currency: string }[]
      }
      expect(body.sections.map((s) => s.transaction_ids)).toEqual([
        ["one"],
        ["two"],
      ])
      expect(body.sections.map((s) => s.currency)).toEqual(["EUR", "USD"])
      return {
        revision: "b".repeat(64),
        transaction_count: 2,
        explanation: "Originals and saved corrections remain in history.",
        sections: [
          {
            key: "section-1",
            holder: "Example business",
            account_number: "EUR-A",
            currency: "EUR",
            transaction_count: 1,
            incomplete_count: 0,
            credit_minor: "0",
            debit_minor: "40000",
          },
          {
            key: "section-2",
            holder: "Example business",
            account_number: "USD-B",
            currency: "USD",
            transaction_count: 1,
            incomplete_count: 0,
            credit_minor: "50000",
            debit_minor: "0",
          },
        ],
      } as never
    }
    if (String(url).includes("/recovery/save")) {
      expect(options?.body).toMatchObject({ expected_preview: "b".repeat(64) })
      saves++
      return {
        applied: true,
        source_document_id: "source",
        sections: [
          {
            key: "section-1",
            source_document_id: "new-eur",
            currency: "EUR",
            transaction_count: 1,
          },
          {
            key: "section-2",
            source_document_id: "new-usd",
            currency: "USD",
            transaction_count: 1,
          },
        ],
      } as never
    }
    if (String(url).includes("new-usd/details"))
      return {
        case_id: "case",
        source_document_id: "new-usd",
        evidence_file_id: "file",
        account_id: "usd-account",
        period_id: "usd-period",
        revision: "c".repeat(64),
        currency: "USD",
        balance_convention: "asset_balance",
        details: {
          ...input.details,
          account_number: "USD-B",
          institution: "Bank Two",
        },
        pages: [1, 2],
        balances: {
          opening: { amount_minor: null, page: null },
          closing: { amount_minor: null, page: null },
        },
      } as never
    throw Error(`Unexpected request: ${url}`)
  })
  await page.viewport(1280, 900)
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <SavedStatementRecovery caseId="case" sourceId="source" />
    </QueryClientProvider>
  )
  fireEvent.click(
    screen.getByRole("button", {
      name: "Separate account or currency sections",
    })
  )
  await screen.findByLabelText("Section 2 Account number")
  fireEvent.change(screen.getByLabelText("Section 2 Account number"), {
    target: { value: "USD-B" },
  })
  fireEvent.change(screen.getByLabelText("Section 2 Bank"), {
    target: { value: "Bank Two" },
  })
  fireEvent.change(screen.getByLabelText("Section 2 Currency"), {
    target: { value: "USD" },
  })
  fireEvent.click(screen.getByLabelText("Select USD transfer"))
  fireEvent.click(screen.getByRole("button", { name: "Assign 1 selected" }))
  fireEvent.change(
    screen.getByLabelText("Reason for separating these records"),
    {
      target: {
        value: "Checked the two printed account sections against the PDF.",
      },
    }
  )
  fireEvent.click(screen.getByRole("button", { name: "Close and keep draft" }))
  fireEvent.click(
    screen.getByRole("button", {
      name: "Separate account or currency sections",
    })
  )
  expect(await screen.findByLabelText("Section 2 Account number")).toHaveValue(
    "USD-B"
  )
  expect(screen.getByLabelText("Section for USD transfer")).toHaveValue(
    "section-2"
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Review section assignments" })
  )
  await screen.findByRole("region", { name: "Review section changes" })
  expect(
    screen.getByRole("button", { name: "Save 2 separate sections" })
  ).toBeVisible()
  await page.screenshot({ path: "/tmp/loupe-saved-recovery-preview.png" })
  fireEvent.click(
    screen.getByRole("button", { name: "Save 2 separate sections" })
  )
  await screen.findByText(/Saved 2 sections/)
  expect(saves).toBe(1)
  fireEvent.click(
    screen.getByRole("button", { name: "Review saved section 2" })
  )
  await waitFor(() =>
    expect(screen.getByLabelText("Saved account number")).toHaveValue("USD-B")
  )
  expect(screen.getByText("Saved payments for new-usd")).toBeVisible()
  await page.viewport(390, 844)
  await waitFor(() => {
    const bounds = screen.getByRole("dialog").getBoundingClientRect()
    expect(bounds.left).toBeGreaterThanOrEqual(0)
    expect(bounds.right).toBeLessThanOrEqual(390)
  })
  await page.screenshot({ path: "/tmp/loupe-saved-recovery-mobile.png" })
  expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(390)
})

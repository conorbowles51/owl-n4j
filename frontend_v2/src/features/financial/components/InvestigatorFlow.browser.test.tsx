import "@/styles/globals.css"
import "../financial-workspace.css"
import { useState } from "react"
import { MemoryRouter } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  fireEvent,
  render,
  screen,
  within,
  waitFor,
  cleanup,
} from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { page } from "@vitest/browser/context"
import { LedgerRowBrowser } from "./LedgerRowBrowser"
import { LedgerSourceDialog } from "./LedgerSourceDialog"
import { paymentFixture } from "../lib/payment-fixture.test-support"
import { useFinancialDraftStore } from "../stores/financial-drafts"
import type { LedgerTransaction } from "../api"
import { fetchAPI } from "@/lib/api-client"
vi.mock("@/lib/api-client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(),
}))
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({ canEdit: true, canUpload: true }),
}))
vi.mock("./SourceCustodyPanel", () => ({ SourceCustodyPanel: () => null }))
const fileId = "11111111-1111-4111-8111-111111111111"
const incoming: LedgerTransaction = {
  ...paymentFixture,
  key: "incoming",
  ref_id: "TX-IN",
  description: "Wire from GlobalTech Industries",
  from_name: "GlobalTech Industries",
  to_name: "Nexus Trading Ltd",
  account_label: "Nexus Trading Ltd",
  amount_minor: "12500000",
  transaction_date: "2023-03-18",
  ordering_date: "2023-03-18",
  running_balance_minor: "13745000",
}
const outgoing: LedgerTransaction = {
  ...incoming,
  key: "outgoing",
  ref_id: "TX-OUT",
  direction: "debit",
  description: "Transfer to Cayman National Bank",
  from_name: "Nexus Trading Ltd",
  to_name: "Cayman National Bank",
  amount_minor: "12000000",
  transaction_date: "2023-03-20",
  ordering_date: "2023-03-20",
  running_balance_minor: "1745000",
  row_index: 1,
}
const rows = [incoming, outgoing]
const citation = (row: LedgerTransaction) => ({
  case_id: "case",
  transaction_id: row.key,
  ref_id: row.ref_id,
  transaction: row,
  source_document_id: row.source_document_id,
  evidence_file_id: fileId,
  filename: "Synthetic Nexus statement.pdf",
  sha256_at_ingestion: "a".repeat(64),
  recorded_digest_matches: true,
  file_bytes_verified: false,
  locator_state: "stored",
  locator: {
    kind: "page_rectangle",
    page: 1,
    rect: [
      20,
      row.key === "incoming" ? 110 : 150,
      570,
      row.key === "incoming" ? 145 : 185,
    ],
    page_size: [600, 300],
    units: "millipoints",
    space: "pdf_displayed",
  },
  ledger_status: "admitted",
  superseded_by_id: null,
  limitation: "Synthetic acceptance fixture",
})
function Workspace() {
  const [source, setSource] = useState<LedgerTransaction | null>(null)
  return (
    <main className="bg-background p-5 text-foreground min-h-screen">
      <h1 className="mb-4 text-xl font-semibold">
        Transactions · Synthetic acceptance case
      </h1>
      <div className={source ? "grid grid-cols-[1.2fr_1fr] gap-4" : ""}>
        <LedgerRowBrowser
          investigation
          transactions={rows}
          exportContext={{ caseId: "case", params: {} }}
          onSource={setSource}
        />
        {source && (
          <LedgerSourceDialog
            inline
            caseId="case"
            transactionId={source.key}
            onClose={() => setSource(null)}
          />
        )}
      </div>
    </main>
  )
}
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  useFinancialDraftStore.setState({ drafts: {} })
})
it("opens the original, chooses related payments, saves their finding and returns to the same search", async () => {
  await page.viewport(1440, 1000)
  document.documentElement.classList.remove("dark")
  let saved: Record<string, unknown> | undefined
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (url.includes("financial-payment-links"))
      return {
        case_id: "case",
        total: saved ? 1 : 0,
        entries: saved
          ? [
              {
                id: "finding",
                title: "Check destination of March transfer",
                tags: ["financial-question"],
                payment_ids: ["incoming", "outgoing"],
              },
            ]
          : [],
      } as never
    if (url.includes("/ledger/sources?"))
      return {
        case_id: "case",
        sources: (
          options!.body as { transaction_ids: string[] }
        ).transaction_ids.map((id) =>
          citation(rows.find((r) => r.key === id)!)
        ),
      } as never
    if (url.includes("/ledger/incoming/source"))
      return citation(incoming) as never
    if (url.includes("/ledger/outgoing/source"))
      return citation(outgoing) as never
    if (url.includes("/ledger?"))
      return { case_id: "case", total: 2, transactions: rows } as never
    if (url.includes("/ledger-categories"))
      return { case_id: "case", categories: [] } as never
    if (url.endsWith("/entries") && options?.method === "POST") {
      saved = options.body as Record<string, unknown>
      return { id: "finding", case_id: "case", ...saved } as never
    }
    throw Error(`Unexpected fixture request: ${url}`)
  })
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      new Blob(
        [
          `<svg xmlns="http://www.w3.org/2000/svg" width="600" height="300"><rect width="600" height="300" fill="white"/><g fill="black" font-family="Arial" font-size="14"><text x="25" y="40">SYNTHETIC NEXUS STATEMENT — TEST FIXTURE</text><text x="25" y="85">Date / Description                         Credit             Debit</text><text x="25" y="130">18 March 2023 · GlobalTech          125,000 EUR</text><text x="25" y="170">20 March 2023 · Cayman National                     120,000 EUR</text></g></svg>`,
        ],
        { type: "image/svg+xml" }
      )
    )
  )
  render(
    <MemoryRouter>
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
        <Workspace />
      </QueryClientProvider>
    </MemoryRouter>
  )
  fireEvent.change(screen.getByLabelText("Search payments"), {
    target: { value: "GlobalTech" },
  })
  fireEvent.click(
    screen.getByRole("button", { name: "Wire from GlobalTech Industries" })
  )
  await screen.findByRole("img", { name: /Highlighted source of TX-IN/ })
  fireEvent.click(screen.getByRole("button", { name: "Related payments" }))
  const related = await screen.findByRole("checkbox", {
    name: /Compare Transfer to Cayman/,
  })
  fireEvent.click(related)
  await page.screenshot({
    path: "../../../../../output/financial-flow-related-light.png",
  })
  fireEvent.click(
    screen.getByRole("button", { name: "Compare 2 selected payments" })
  )
  const comparison = await screen.findByRole("dialog")
  await within(comparison).findByText("2 days later")
  expect(within(comparison).getByText("5,000.00 EUR")).toBeVisible()
  fireEvent.click(
    within(comparison).getByRole("button", {
      name: "Create finding from these payments",
    })
  )
  const finding = await screen.findByRole("dialog")
  fireEvent.change(within(finding).getByLabelText("Title"), {
    target: { value: "Check destination of March transfer" },
  })
  fireEvent.change(within(finding).getByLabelText("Explanation"), {
    target: {
      value:
        "Who received the EUR 120,000 two days after the receipt? Obtain the destination account record.",
    },
  })
  expect(within(finding).getByText(/2 supporting payments/)).toBeVisible()
  await page.screenshot({
    path: "../../../../../output/financial-flow-finding-light.png",
  })
  fireEvent.click(within(finding).getByRole("button", { name: "Save finding" }))
  await within(finding).findByText(/Saved to this case/)
  expect(
    (
      saved?.links as {
        source_anchor: { financial_transaction_ids: string[] }
      }[]
    )[0].source_anchor.financial_transaction_ids
  ).toEqual(["incoming", "outgoing"])
  fireEvent.click(
    within(finding).getByRole("button", { name: "Return to investigation" })
  )
  fireEvent.click(
    screen.getByRole("dialog").querySelector('[aria-label="Close"]') ??
      within(screen.getByRole("dialog")).getByRole("button", { name: "Close" })
  )
  expect(screen.getByLabelText("Search payments")).toHaveValue("GlobalTech")
  await waitFor(() =>
    expect(screen.getAllByText(/1 linked findings/).length).toBeGreaterThan(0)
  )
}, 30000)

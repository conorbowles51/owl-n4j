import "@/styles/globals.css"
import { page } from "vitest/browser"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { ImportedStatementDetails } from "./ImportedStatementDetails"

vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
vi.mock("./TransactionSourceHighlight", () => ({
  TransactionSourceHighlight: () => (
    <div className="min-h-[450px] bg-white border p-8 space-y-6 text-slate-800">
      <h2 className="text-xl font-bold">Example statement</h2>
      <p>Synthetic PDF placeholder for testing the editing layout.</p>
      <p>Opening balance: EUR 60.00</p>
      <p>Fee: EUR 30.00 · Tax: EUR 4.80</p>
      <p>Closing balance: EUR 25.20</p>
    </div>
  ),
}))

it("keeps the statement and correction fields together, then reopens saved values", async () => {
  const initial = {
    case_id: "case",
    source_document_id: "source",
    evidence_file_id: "file",
    account_id: "account",
    period_id: "period",
    revision: "a".repeat(64),
    currency: "EUR",
    balance_convention: "asset_balance",
    details: {
      holder: "Example company",
      account_number: "",
      institution: "Example bank",
    },
    pages: [1, 2],
    balances: {
      opening: { amount_minor: null, page: null },
      closing: { amount_minor: null, page: null },
    },
  }
  let stored: unknown = initial
  vi.mocked(fetchAPI).mockImplementation(async (_url, options) => {
    if (options?.method === "PUT") {
      const body = options.body as Record<string, unknown>
      expect(body).toMatchObject({
        account_number: "00123456789", currency: "MXN", period_start: "2024-09-01", period_end: "2024-09-30",
        opening: { amount_minor: "6000", page: 1 },
        closing: { amount_minor: "2520", page: 1 },
      })
      stored = {
        ...initial,
        revision: "b".repeat(64),
        currency: body.currency,
        details: { ...initial.details, account_number: body.account_number, period_start: body.period_start, period_end: body.period_end },
        balances: { opening: body.opening, closing: body.closing },
        admission: {
          can_import: false, status: "needs_review",
          blockers: [{ message: "Review the unread source row before confirming these checks." }],
          calculation: {
            available: true, currency: "MXN", balance_convention: "asset_balance",
            opening_minor: "6000", credit_minor: "0", debit_minor: "3480",
            calculated_closing_minor: "2520", printed_closing_minor: "2520", difference_minor: "0",
          },
        },
      }
    }
    return stored as never
  })
  await page.viewport(1200, 820)
  document.documentElement.classList.remove("dark")
  const mount = () => render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <main className="p-5 bg-background text-foreground">
        <h1 className="font-semibold text-lg mb-4">Statement and balances</h1>
        <ImportedStatementDetails caseId="case" sourceId="source" withSource />
      </main>
    </QueryClientProvider>
  )
  mount()
  fireEvent.click(
    screen.getByRole("button", { name: "Edit account, dates, currency and balances" })
  )
  await screen.findByLabelText("Saved account number")
  const originalUrl = window.location.href
  fireEvent.change(screen.getByLabelText("Saved account number"), {
    target: { value: "00123456789" },
  })
  for (const [role, value] of [
    ["opening", "60.00"],
    ["closing", "25.20"],
  ]) {
    fireEvent.change(screen.getByLabelText(`Saved ${role} balance`), {
      target: { value },
    })
    fireEvent.change(screen.getByLabelText(`${role} balance page`), {
      target: { value: "1" },
    })
  }
  fireEvent.change(screen.getByLabelText("Saved statement currency"), { target: { value: "MXN" } })
  fireEvent.change(screen.getByLabelText("Saved period start"), { target: { value: "2024-09-01" } })
  fireEvent.change(screen.getByLabelText("Saved period end"), { target: { value: "2024-09-30" } })
  // Leave the view with unfinished changes, then return to the same statement.
  cleanup()
  mount()
  fireEvent.click(screen.getByRole("button", { name: "Edit account, dates, currency and balances" }))
  await screen.findByLabelText("Saved period start")
  expect(screen.getByLabelText("Saved period start")).toHaveValue("2024-09-01")
  expect(screen.getByLabelText("Saved statement currency")).toHaveValue("MXN")
  expect(screen.getByText("Example statement")).toBeVisible()
  await page.screenshot({ path: "/tmp/imported-statement-edit-light.png" })
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }))
  await screen.findByText(/Changes saved/)
  const checks = screen.getByLabelText("Saved statement checks")
  expect(checks).toHaveTextContent("Saved opening balance60.00 MXN")
  expect(checks).toHaveTextContent("Saved closing balance25.20 MXN")
  expect(checks).toHaveTextContent("Money in0.00 MXN")
  expect(checks).not.toHaveTextContent("MXN MXN")
  expect(checks).toHaveTextContent("Review the unread source row before confirming these checks.")
  fireEvent.click(
    screen.getByRole("button", { name: "Edit account, dates, currency and balances" })
  )
  expect(await screen.findByLabelText("Saved account number")).toHaveValue(
    "00123456789"
  )
  expect(screen.getByLabelText("Saved opening balance")).toHaveValue("60.00")
  expect(screen.getByLabelText("Saved closing balance")).toHaveValue("25.20")
  expect(screen.getByLabelText("Saved period end")).toHaveValue("2024-09-30")
  expect(screen.getByLabelText("Saved statement currency")).toHaveValue("MXN")
  expect(window.location.href).toBe(originalUrl)
})

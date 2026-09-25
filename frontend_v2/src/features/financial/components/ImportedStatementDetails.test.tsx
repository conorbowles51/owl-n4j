import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { ImportedStatementDetails } from "./ImportedStatementDetails"
import { fetchAPI } from "@/lib/api-client"
import { useInvestigationScopeStore } from "../stores/investigation-scope"
import { useFinancialDraftStore } from "../stores/financial-drafts"
vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
vi.mock("./TransactionSourceHighlight", () => ({
  TransactionSourceHighlight: () => (
    <div>Original PDF stays beside these fields</div>
  ),
}))
afterEach(() => {
  cleanup()
  vi.resetAllMocks()
  useInvestigationScopeStore.getState().reset()
  useFinancialDraftStore.setState({ drafts: {} })
})
const initial = () => ({
  case_id: "case",
  source_document_id: "source",
  evidence_file_id: "file",
  account_id: "account",
  period_id: "period",
  revision: "a".repeat(64),
  currency: "EUR",
  balance_convention: "asset_balance",
  details: { holder: "Titanium", account_number: "", institution: "BBVA" },
  pages: [2, 3],
  balances: {
    opening: { amount_minor: null, page: null },
    closing: { amount_minor: null, page: null },
  },
})
function mount() {
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <ImportedStatementDetails caseId="case" sourceId="source" withSource />
    </QueryClientProvider>
  )
}
it("opens legacy saved details with a specific blocker when no calculation can be made", async () => {
  vi.mocked(fetchAPI).mockResolvedValue({
    ...initial(),
    admission: {
      can_import: false, status: "needs_review", calculation: null,
      blockers: [{ message: "Choose the printed currency before checking the balances." }],
    },
  } as never)
  mount()
  expect(await screen.findByText("Choose the printed currency before checking the balances.")).toBeVisible()
  fireEvent.click(screen.getByRole("button", { name: "Edit account, dates, currency and balances" }))
  expect(screen.getByLabelText("Saved statement currency")).toBeEnabled()
})
it("explains a saved but unconfirmed quiet period instead of implying the checks passed", async () => {
  const data = { ...initial(), has_payment_readings: false }
  const checked = {
    ...data,
    revision: "b".repeat(64),
    admission: {
      status: "needs_review",
      can_import: false,
      blockers: [
        {
          message:
            "Check the printed closing balance against the opening balance.",
        },
      ],
    },
  }
  let stored = data
  vi.mocked(fetchAPI).mockImplementation(async (_url, options) => {
    if (options?.method === "PUT") {
      expect(options.body).toMatchObject({ no_activity_confirmed: true })
      stored = checked
    }
    return stored as never
  })
  mount()
  fireEvent.click(
    screen.getByRole("button", {
      name: "Edit account, dates, currency and balances",
    })
  )
  fireEvent.click(
    await screen.findByRole("checkbox", { name: /I checked every page/ })
  )
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }))
  await screen.findByText(/Changes saved/)
  expect(screen.getByLabelText("Saved statement checks")).toHaveTextContent(
    "Details are saved, but the statement still needs review."
  )
  expect(screen.getByLabelText("Saved statement checks")).toHaveTextContent(
    checked.admission.blockers[0].message
  )
  cleanup()
  mount()
  await screen.findByText(checked.admission.blockers[0].message)
  expect(
    screen.queryByText(/No activity confirmed at the last save/)
  ).not.toBeInTheDocument()
})
it("shows saved denomination once and keeps a quiet confirmation blocker after currency correction", async () => {
  const admission = {
    can_import: false,
    status: "needs_review",
    blockers: [{ message: "Confirm that every page has no transactions." }],
    calculation: {
      available: true, currency: "USD", balance_convention: "asset_balance",
      opening_minor: "720500", credit_minor: "0", debit_minor: "0",
      calculated_closing_minor: "720500", printed_closing_minor: "720500", difference_minor: "0",
    },
  }
  let stored = { ...initial(), has_payment_readings: false, admission: {
    ...admission, calculation: { ...admission.calculation, currency: "EUR" },
  },
    balances: { opening: { amount_minor: "720500", page: 2 }, closing: { amount_minor: "720500", page: 2 } } }
  vi.mocked(fetchAPI).mockImplementation(async (_url, options) => {
    if (options?.method === "PUT") {
      expect(options.body).toMatchObject({ currency: "USD" })
      expect(options.body).not.toHaveProperty("no_activity_confirmed", true)
      stored = { ...stored, currency: "USD", admission, revision: "b".repeat(64) }
    }
    return stored as never
  })
  mount()
  fireEvent.click(screen.getByRole("button", { name: "Edit account, dates, currency and balances" }))
  fireEvent.change(await screen.findByLabelText("Saved statement currency"), { target: { value: "USD" } })
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }))
  await screen.findByText(/Changes saved/)
  const checks = screen.getByLabelText("Saved statement checks")
  expect(checks).toHaveTextContent("Saved opening balance7205.00 USD")
  expect(checks).toHaveTextContent("Saved closing balance7205.00 USD")
  expect(checks).toHaveTextContent("Money in0.00 USD")
  expect(checks).not.toHaveTextContent("USD USD")
  expect(checks).not.toHaveTextContent("Printed opening balance")
  expect(checks).toHaveTextContent(admission.blockers[0].message)
  cleanup()
  mount()
  expect(await screen.findByLabelText("Saved statement checks")).toHaveTextContent("7205.00 USD")
})
it("edits account and balances beside the PDF, saves and reopens without losing leading zeros", async () => {
  useInvestigationScopeStore
    .getState()
    .apply("case", { accountId: "account", startDate: "2024-09-01" })
  let stored: unknown = initial()
  vi.mocked(fetchAPI).mockImplementation(async (_url, options) => {
    if (options?.method === "PUT") {
      const body = options.body as Record<string, unknown>
      expect(body).toMatchObject({
        account_number: "00123448932",
        opening: { amount_minor: "6000", page: 2 },
        closing: { amount_minor: "2520", page: 2 },
      })
      stored = {
        ...initial(),
        account_id: "corrected-account",
        revision: "b".repeat(64),
        details: { ...initial().details, account_number: body.account_number },
        balances: { opening: body.opening, closing: body.closing },
      }
    }
    return stored as never
  })
  mount()
  fireEvent.click(
    screen.getByRole("button", {
      name: "Edit account, dates, currency and balances",
    })
  )
  await screen.findByLabelText("Saved account number")
  expect(
    screen.getByText("Original PDF stays beside these fields")
  ).toBeVisible()
  fireEvent.change(screen.getByLabelText("Saved account number"), {
    target: { value: "00123448932" },
  })
  for (const [role, value] of [
    ["opening", "60.00"],
    ["closing", "25.20"],
  ]) {
    fireEvent.change(screen.getByLabelText(`Saved ${role} balance`), {
      target: { value },
    })
    fireEvent.change(screen.getByLabelText(`${role} balance page`), {
      target: { value: "2" },
    })
  }
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }))
  await screen.findByText(/Changes saved/)
  expect(
    Object.values(useInvestigationScopeStore.getState().scopes)
  ).toContainEqual({
    accountId: "corrected-account",
    startDate: "2024-09-01",
    endDate: undefined,
  })
  cleanup()
  mount()
  fireEvent.click(
    screen.getByRole("button", {
      name: "Edit account, dates, currency and balances",
    })
  )
  expect(await screen.findByLabelText("Saved account number")).toHaveValue(
    "00123448932"
  )
  expect(screen.getByLabelText("Saved opening balance")).toHaveValue("60.00")
  expect(screen.getByLabelText("Saved closing balance")).toHaveValue("25.20")
})
it("retains edits after a failed save and requires a page only for changed balances", async () => {
  vi.mocked(fetchAPI).mockImplementation(async (_url, options) => {
    if (options?.method === "PUT")
      throw Error("Another reviewer changed these details.")
    return initial() as never
  })
  mount()
  fireEvent.click(
    screen.getByRole("button", {
      name: "Edit account, dates, currency and balances",
    })
  )
  await screen.findByLabelText("Saved account number")
  fireEvent.change(screen.getByLabelText("Saved account number"), {
    target: { value: "00123" },
  })
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }))
  expect(await screen.findByRole("alert")).toHaveTextContent("Another reviewer")
  expect(screen.getByLabelText("Saved account number")).toHaveValue("00123")
  fireEvent.change(screen.getByLabelText("Saved opening balance"), {
    target: { value: "0.00" },
  })
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }))
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent("select its PDF page")
  )
  expect(
    vi
      .mocked(fetchAPI)
      .mock.calls.filter(([, options]) => options?.method === "PUT")
  ).toHaveLength(1)
})

it.each(["GBP", "JPY", "KWD", "CLF"])(
  "corrects saved currency to %s without changing printed numbers",
  async (currency) => {
    const data = {
      ...initial(),
      balances: {
        opening: { amount_minor: "6000", page: 2 },
        closing: { amount_minor: "2520", page: 2 },
      },
    }
    vi.mocked(fetchAPI).mockImplementation(async (_url, options) => {
      if (options?.method === "PUT") {
        expect(options.body).toMatchObject({
          currency,
          expected_revision: data.revision,
        })
        expect(options.body).not.toHaveProperty("opening")
        expect(options.body).not.toHaveProperty("closing")
        return { ...data, currency, revision: "b".repeat(64) } as never
      }
      return data as never
    })
    mount()
    fireEvent.click(
      screen.getByRole("button", {
        name: "Edit account, dates, currency and balances",
      })
    )
    fireEvent.change(await screen.findByLabelText("Saved statement currency"), {
      target: { value: currency },
    })
    expect(screen.getByLabelText("Saved opening balance")).toHaveValue("60.00")
    expect(screen.getByLabelText("Saved closing balance")).toHaveValue("25.20")
    expect(screen.getByText(/no exchange-rate conversion/)).toBeVisible()
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }))
    await screen.findByText(/Changes saved/)
  }
)

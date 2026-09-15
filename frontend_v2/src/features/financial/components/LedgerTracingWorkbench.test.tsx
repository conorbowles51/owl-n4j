import { useFinancialDraftStore } from "../stores/financial-drafts"
import {
  render as renderUI,
  screen,
  fireEvent,
  waitFor,
  act,
} from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactNode } from "react"
import { beforeEach, describe, it, expect, vi } from "vitest"
import { LedgerTracingWorkbench } from "./LedgerTracingWorkbench"
import { fetchAPI } from "@/lib/api-client"
function render(ui: ReactNode, client = new QueryClient()) {
  return renderUI(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>
  )
}
vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
vi.mock("./RequestedCoveragePanel", () => ({
  RequestedCoveragePanel: () => null,
}))
vi.mock("./LedgerFilters", () => ({
  LedgerFilters: ({ onApply }: { onApply: (p: unknown) => void }) => (
    <button
      onClick={() =>
        onApply({
          accountId: "account",
          startDate: "2026-01-01",
          endDate: "2026-01-31",
        })
      }
    >
      Apply scope
    </button>
  ),
}))
beforeEach(() => {
  useFinancialDraftStore.setState({ drafts: {} })
  vi.mocked(fetchAPI).mockReset()
})
const inputs = {
  case_id: "case",
  account_id: "account",
  start_date: "2026-01-01",
  end_date: "2026-01-31",
  currency: "GBP",
  snapshot_sha256: "a".repeat(64),
  included_rows: 1,
  excluded_rows: 0,
  applied: false,
  readings: [
    {
      included: true,
      row: {
        key: "row",
        ordering_date: "2026-01-15",
        direction: "credit",
        amount_minor: "100",
        description: "Deposit",
        currency: "GBP",
      },
    },
  ],
}
describe("conditional tracing workbench", () => {
  it("requires a reload after case payments refresh without deleting opening assumptions", async () => {
    vi.mocked(fetchAPI).mockResolvedValue(inputs)
    const client = new QueryClient()
    render(<LedgerTracingWorkbench caseId="case" />, client)
    fireEvent.click(screen.getByRole("button", { name: "Apply scope" }))
    fireEvent.click(screen.getByRole("button", { name: "Load tracing inputs" }))
    await screen.findByText("Record your scenario assumptions")
    fireEvent.change(screen.getByLabelText("Opening balance (GBP)"), {
      target: { value: "25.00" },
    })
    await act(async () => {
      await client.invalidateQueries({ queryKey: ["financial-ledger", "case"] })
    })
    expect(screen.getByText(/Payments may have changed/)).toBeVisible()
    expect(
      screen.queryByRole("button", { name: "Calculate conditional scenario" })
    ).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Load tracing inputs" }))
    await screen.findByText("Record your scenario assumptions")
    expect(screen.getByLabelText("Opening balance (GBP)")).toHaveValue("25.00")
    expect(
      screen.queryByText(/Payments may have changed/)
    ).not.toBeInTheDocument()
  })
  it("requires scope and explicit assumptions, with no selected method", async () => {
    vi.mocked(fetchAPI).mockResolvedValue(inputs)
    render(<LedgerTracingWorkbench caseId="case" />)
    expect(
      screen.getByRole("button", { name: "Load tracing inputs" })
    ).toBeDisabled()
    fireEvent.click(screen.getByRole("button", { name: "Apply scope" }))
    fireEvent.click(screen.getByRole("button", { name: "Load tracing inputs" }))
    await screen.findByText("Record your scenario assumptions")
    expect(
      screen.getByLabelText("Attributed deposit").querySelectorAll("option")
    ).toHaveLength(2)
    expect(screen.getByLabelText("Opening balance (GBP)")).toHaveValue("")
    expect(
      screen.getByRole("button", { name: "Calculate conditional scenario" })
    ).toBeDisabled()
    screen
      .getAllByRole("checkbox")
      .forEach((box) => expect(box).not.toBeChecked())
  })
  it("refuses inputs for another case", async () => {
    vi.mocked(fetchAPI).mockResolvedValue({ ...inputs, case_id: "other" })
    render(<LedgerTracingWorkbench caseId="case" />)
    fireEvent.click(screen.getByRole("button", { name: "Apply scope" }))
    fireEvent.click(screen.getByRole("button", { name: "Load tracing inputs" }))
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent("different filters")
    )
    expect(
      screen.queryByText("Record your scenario assumptions")
    ).not.toBeInTheDocument()
  })
})

it("adds and removes deposit attributions without losing another claim", async () => {
  vi.mocked(fetchAPI).mockResolvedValue(inputs)
  render(<LedgerTracingWorkbench caseId="case" />)
  fireEvent.click(screen.getByRole("button", { name: "Apply scope" }))
  fireEvent.click(screen.getByRole("button", { name: "Load tracing inputs" }))
  await screen.findByLabelText("Claim label")
  fireEvent.change(screen.getByLabelText("Claim label"), {
    target: { value: "First claim" },
  })
  fireEvent.click(
    screen.getByRole("button", { name: "Add deposit attribution" })
  )
  fireEvent.change(await screen.findByLabelText("Claim label 2"), {
    target: { value: "Second claim" },
  })
  fireEvent.click(screen.getByRole("button", { name: "Remove attribution 1" }))
  expect(screen.getByLabelText("Claim label")).toHaveValue("Second claim")
  expect(screen.queryByLabelText("Claim label 2")).not.toBeInTheDocument()
})
it("changing tracing population discards the old assumptions", async () => {
  vi.mocked(fetchAPI).mockResolvedValue(inputs)
  render(<LedgerTracingWorkbench caseId="case" />)
  fireEvent.click(screen.getByRole("button", { name: "Apply scope" }))
  fireEvent.click(screen.getByRole("button", { name: "Load tracing inputs" }))
  await screen.findByLabelText("Claim label")
  fireEvent.change(screen.getByLabelText("Tracing population"), {
    target: { value: "working" },
  })
  expect(screen.queryByLabelText("Claim label")).not.toBeInTheDocument()
})

it("converts decimal currency inputs exactly before submitting the scenario", async () => {
  vi.mocked(fetchAPI).mockClear()
  vi.mocked(fetchAPI)
    .mockResolvedValueOnce(inputs)
    .mockRejectedValueOnce(new Error("Synthetic response"))
  render(<LedgerTracingWorkbench caseId="case" />)
  fireEvent.click(screen.getByRole("button", { name: "Apply scope" }))
  fireEvent.click(screen.getByRole("button", { name: "Load tracing inputs" }))
  await screen.findByLabelText("Opening balance (GBP)")
  for (const [label, value] of [
    ["Opening balance (GBP)", "90071992547409.93"],
    ["Opening balance basis", "Explicit assumption"],
    ["Basis for accepting this movement order", "Checked source"],
    ["Attributed deposit", "row"],
    ["Claim label", "Claim"],
    ["Attributed amount (GBP)", "0.50"],
    ["Attribution basis", "Explicit attribution"],
  ])
    fireEvent.change(screen.getByLabelText(label), { target: { value } })
  fireEvent.click(
    screen.getByRole("checkbox", { name: /^First in, first out/ })
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Calculate conditional scenario" })
  )
  await screen.findByText("Synthetic response")
  const call = vi
    .mocked(fetchAPI)
    .mock.calls.find(([url]) => String(url).includes("/ledger-trace?"))!
  expect(call[1]?.body).toMatchObject({
    opening_balance_minor: "9007199254740993",
    attributions: [
      { transaction_id: "row", claim_id: "Claim", amount_minor: "50" },
    ],
  })
})

it("restores tracing assumptions only for the same loaded payments", async () => {
  vi.mocked(fetchAPI).mockResolvedValue(inputs)
  const first = render(<LedgerTracingWorkbench caseId="case" />)
  fireEvent.click(screen.getByRole("button", { name: "Apply scope" }))
  fireEvent.click(screen.getByRole("button", { name: "Load tracing inputs" }))
  await screen.findByLabelText("Opening balance (GBP)")
  fireEvent.change(screen.getByLabelText("Opening balance (GBP)"), {
    target: { value: "220.00" },
  })
  fireEvent.change(screen.getByLabelText("Opening balance basis"), {
    target: { value: "Opening amount on page 1" },
  })
  fireEvent.change(screen.getByLabelText("Claim label"), {
    target: { value: "Deposit being investigated" },
  })
  fireEvent.click(
    screen.getByRole("checkbox", { name: /^First in, first out/ })
  )
  first.unmount()
  const next = render(<LedgerTracingWorkbench caseId="case" />)
  fireEvent.click(screen.getByRole("button", { name: "Load tracing inputs" }))
  expect(await screen.findByLabelText("Opening balance (GBP)")).toHaveValue(
    "220.00"
  )
  expect(screen.getByLabelText("Opening balance basis")).toHaveValue(
    "Opening amount on page 1"
  )
  expect(screen.getByLabelText("Claim label")).toHaveValue(
    "Deposit being investigated"
  )
  expect(
    screen.getByRole("checkbox", { name: /^First in, first out/ })
  ).toBeChecked()
  expect(
    screen.queryByRole("button", { name: "Download conditional scenario" })
  ).not.toBeInTheDocument()
  next.unmount()
  vi.mocked(fetchAPI).mockResolvedValue({
    ...inputs,
    snapshot_sha256: "b".repeat(64),
  })
  render(<LedgerTracingWorkbench caseId="case" />)
  fireEvent.click(screen.getByRole("button", { name: "Load tracing inputs" }))
  expect(await screen.findByLabelText("Opening balance (GBP)")).toHaveValue("")
  expect(screen.getByLabelText("Claim label")).toHaveValue("")
})

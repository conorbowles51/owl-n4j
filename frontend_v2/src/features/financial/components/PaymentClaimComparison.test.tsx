import { act, cleanup, fireEvent, render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { useFinancialDraftStore } from "../stores/financial-drafts"
import fixture from "../lib/claim-comparison.fixture.json"
import { PaymentClaimComparison } from "./PaymentClaimComparison"

const captured = JSON.parse(fixture.scenario_json)
vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
vi.mock("./LedgerFilters", () => ({
  LedgerFilters: ({
    onApply,
  }: {
    onApply: (value: { accountId: string }) => void
  }) => (
    <button onClick={() => onApply({ accountId: captured.inputs.account_id })}>
      Choose test account
    </button>
  ),
}))
vi.mock("./ClaimEvidencePicker", () => ({
  ClaimEvidencePicker: ({
    onChange,
  }: {
    onChange: (value: { id: string; label: string }) => void
  }) => (
    <button
      onClick={() =>
        onChange({
          id: captured.inputs.source_file_id,
          label: "Synthetic interview",
        })
      }
    >
      Choose test source
    </button>
  ),
}))
vi.mock("./RequestedCoveragePanel", () => ({
  RequestedCoveragePanel: () => null,
}))
vi.mock("./ClaimComparisonDecision", () => ({
  ClaimComparisonDecision: () => (
    <button>Save claim review with sources</button>
  ),
}))
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  useFinancialDraftStore.setState({ drafts: {} })
})

it("hides an outdated claim comparison and retains its quotation for a fresh comparison", async () => {
  vi.mocked(fetchAPI).mockResolvedValue(fixture)
  const client = new QueryClient()
  render(
    <QueryClientProvider client={client}>
      <PaymentClaimComparison caseId={captured.case_id} />
    </QueryClientProvider>
  )
  fireEvent.click(screen.getByRole("button", { name: "Choose test account" }))
  fireEvent.click(screen.getByRole("button", { name: "Choose test source" }))
  const fields: Record<string, string> = {
    "Original claim quotation": captured.inputs.quote,
    "Source page, paragraph or time": captured.inputs.source_location,
    "Payer as named": captured.inputs.payer,
    "Payee as named": captured.inputs.payee,
    "Account holder assumption": captured.inputs.account_holder,
    "Claim amount from": "100.00",
    "Claim amount through": "100.00",
    "Claim earliest date": captured.inputs.earliest,
    "Claim latest date": captured.inputs.latest,
    "Claim interpretation basis": captured.inputs.interpretation_basis,
  }
  for (const [label, value] of Object.entries(fields))
    fireEvent.change(screen.getByLabelText(label), { target: { value } })
  fireEvent.change(screen.getByLabelText("Claim comparison population"), {
    target: { value: "working" },
  })
  fireEvent.click(
    screen.getByRole("button", { name: "Find matching payments" })
  )
  await screen.findByRole("region", { name: "Payment claim comparison result" })
  expect(
    screen.getByRole("button", { name: "Save claim review with sources" })
  ).toBeVisible()
  await act(async () => {
    await client.invalidateQueries({
      queryKey: ["financial-ledger", captured.case_id],
    })
  })
  expect(screen.getByText(/Payments may have changed/)).toBeVisible()
  expect(
    screen.queryByRole("button", { name: "Save claim review with sources" })
  ).not.toBeInTheDocument()
  expect(
    screen.queryByRole("button", {
      name: "Download claim comparison with sources",
    })
  ).not.toBeInTheDocument()
  expect(screen.getByLabelText("Original claim quotation")).toHaveValue(
    captured.inputs.quote
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Find matching payments" })
  )
  await screen.findByRole("region", { name: "Payment claim comparison result" })
  expect(
    screen.queryByText(/Payments may have changed/)
  ).not.toBeInTheDocument()
  expect(
    screen.getByRole("button", { name: "Save claim review with sources" })
  ).toBeVisible()
})

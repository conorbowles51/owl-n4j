import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { caseCostsAPI } from "../costs-api"
import { CaseCostsSection } from "./CaseCostsSection"

vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))

const report = {
  case_id: "case-1",
  case_title: "Smith v. Jones",
  start_date: null,
  end_date: null,
  lines: [
    { kind: "Document reading", label: "bank-march.pdf", evidence_file_id: "f1", calls: 91, tokens: 1000,
      models: ["gpt-4o"], cost_usd: 1.25, cost_exact: "1.250000", first_at: "2026-03-01T10:00:00Z",
      last_at: "2026-03-01T10:05:00Z" },
    { kind: "AI assistant", label: "AI assistant conversation c0ffee00", evidence_file_id: null, calls: 3,
      tokens: 10, models: ["gpt-4o"], cost_usd: 0.3, cost_exact: "0.300000", first_at: "2026-03-02T10:00:00Z",
      last_at: "2026-03-04T10:00:00Z" },
  ],
  line_count: 2,
  call_count: 94,
  total_tokens: 1010,
  total_cost_usd: 1.55,
  total_cost_exact: "1.550000",
  generated_at: "2026-11-04T09:00:00Z",
}

const renderSection = () =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <CaseCostsSection caseId="case-1" caseTitle="Smith v. Jones" />
    </QueryClientProvider>
  )

beforeEach(() => vi.mocked(fetchAPI).mockReset())

it("shows one line per document with the calls it folds, and the case total", async () => {
  vi.mocked(fetchAPI).mockResolvedValue(report)
  renderSection()
  expect(await screen.findByText("bank-march.pdf")).toBeTruthy()
  expect(screen.getByText("91")).toBeTruthy()
  expect(screen.getByText("2026-03-02 to 2026-03-04")).toBeTruthy()
  expect(screen.getByTestId("case-costs-total").textContent).toContain("2 lines (94 AI calls)")
  expect(String(vi.mocked(fetchAPI).mock.calls[0][0])).toBe("/api/cost-ledger/case-report?case_id=case-1")
})

it("asks again for the chosen dates", async () => {
  vi.mocked(fetchAPI).mockResolvedValue(report)
  renderSection()
  await screen.findByText("bank-march.pdf")
  fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-03-02" } })
  await waitFor(() =>
    expect(vi.mocked(fetchAPI).mock.calls.some(([url]) => String(url).includes("start_date=2026-03-02"))).toBe(true)
  )
})

it("says why when the costs are refused", async () => {
  const refused = vi.spyOn(caseCostsAPI, "report").mockRejectedValue(new Error("Access denied"))
  renderSection()
  expect(await screen.findByText("Access denied")).toBeTruthy()
  refused.mockRestore()
})

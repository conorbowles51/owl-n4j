vi.mock("../hooks/use-financial-access", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../hooks/use-financial-access")>()),
  useFinancialAccess: () => ({ canEdit: true, canUpload: false, ready: true, error: false }),
}))
vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import type { Judgement } from "../lib/judgements"
import { JudgementMarker, PeriodJudgements } from "./JudgementCalls"

const judgement: Judgement = {
  id: "j-1",
  case_id: "case-a",
  subject_type: "statement_period",
  subject_id: "p-1",
  source_document_id: "d-1",
  statement_period_id: "p-1",
  evidence_file_id: null,
  filename: "08 BBVA AGO 2023.pdf",
  rule_id: "L8.unprinted_opening",
  rule_label: "Opening balance worked back from the closing",
  rule_source: "fin-queue3 L8",
  target_key: "opening_balance",
  origin: "processor",
  strength: "inferred",
  summary: "Opening 12,340.00 is not printed in these pages: it is the closing 15,000.00 less this period's payments.",
  page: 2,
  category: "balance",
  category_label: "Balance or opening worked out",
  priority: 1,
  priority_label: "Check first",
  priority_reason: "an opening balance was worked out, not printed",
  status: "open",
  resolved_by: null,
  resolved_at: null,
  resolution_reason: null,
  adjudication_id: null,
}

function show(onCorrect = vi.fn()) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <JudgementMarker caseId="case-a" judgement={judgement} onCorrect={onCorrect} />
    </QueryClientProvider>
  )
  return onCorrect
}

it("shows the call in plain words and answers it at the right endpoints", async () => {
  const api = vi.mocked(fetchAPI)
  api.mockResolvedValue({ ...judgement, status: "confirmed" })
  const onCorrect = show()
  fireEvent.click(screen.getByRole("button", { name: /Inferred/ }))
  expect(screen.getByText(/Opening 12,340.00 is not printed/)).toBeVisible()
  // The tier is said in words, not colour alone, with why it sits there.
  expect(screen.getAllByTestId("judgement-priority")[0]).toHaveTextContent("Check first")
  expect(screen.getByText(/Here, an opening balance was worked out, not printed\./)).toBeVisible()
  expect(screen.queryByText(/L8/)).toBeNull()
  expect(screen.getByTitle(/L8.unprinted_opening/)).toBeVisible()
  fireEvent.click(screen.getByRole("button", { name: "Looks right" }))
  await waitFor(() =>
    expect(api).toHaveBeenCalledWith("/api/financial/judgements/j-1/confirm?case_id=case-a", { method: "POST", body: {} })
  )
  fireEvent.click(screen.getByRole("button", { name: "Correct it" }))
  expect(onCorrect).toHaveBeenCalledWith(judgement)
  const record = screen.getByRole("button", { name: "Record the correction" })
  expect(record).toBeDisabled()
  fireEvent.change(screen.getByLabelText("Why the processor was wrong"), {
    target: { value: "The July statement prints 12,430.00" },
  })
  fireEvent.click(record)
  await waitFor(() =>
    expect(api).toHaveBeenCalledWith("/api/financial/judgements/j-1/correct?case_id=case-a", {
      method: "POST",
      body: { reason: "The July statement prints 12,430.00" },
    })
  )
})

it("shows a hand entry as its own button, with its own help and the working notes behind a toggle", () => {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <JudgementMarker
        caseId="case-a"
        judgement={{
          ...judgement,
          origin: "agent",
          strength: "proved",
          rule_id: "agent.page_entry",
          summary: "Its 156 payments were entered by hand from the page images.",
          working_notes: "156 movements from page images",
        }}
      />
    </QueryClientProvider>
  )
  const marker = screen.getByRole("button", { name: /Hand entry.*Why\?/ })
  expect(marker).toHaveAttribute("aria-expanded", "false")
  fireEvent.click(marker)
  expect(marker).toHaveAttribute("aria-expanded", "true")
  expect(screen.getByText(/checked against the printed balances and totals/)).toBeVisible()
  expect(screen.queryByText(/Checked guess/)).toBeNull()
  expect(screen.getByText("Working notes")).toBeVisible()
})

it("keeps no list query for a closed period (a statement table renders one per period), and reads it on opening", async () => {
  const client = new QueryClient()
  vi.mocked(fetchAPI).mockReset()
  vi.mocked(fetchAPI).mockImplementation(async (url: string) =>
    url.includes("/judgements/counts")
      ? { case: { total: 2 }, statements: {}, periods: { "p-1": { total: 1 }, "p-2": { total: 1 } }, rules: [] }
      : { items: [judgement] }
  )
  render(
    <QueryClientProvider client={client}>
      <PeriodJudgements caseId="case-a" periodId="p-1" />
      <PeriodJudgements caseId="case-a" periodId="p-2" />
    </QueryClientProvider>
  )
  const buttons = await screen.findAllByRole("button", { name: /1 judgement call/ })
  expect(buttons).toHaveLength(2)
  // Only the shared counts query: no entry per closed period.
  expect(client.getQueryCache().getAll()).toHaveLength(1)
  fireEvent.click(buttons[0])
  await waitFor(() =>
    expect(vi.mocked(fetchAPI).mock.calls.filter(([url]) => String(url).includes("statement_period_id=p-1"))).toHaveLength(1)
  )
  await waitFor(() => expect(screen.queryByRole("status")).toBeNull())
  expect(vi.mocked(fetchAPI).mock.calls.filter(([url]) => String(url).includes("statement_period_id=p-2"))).toHaveLength(0)
  expect(client.getQueryCache().getAll()).toHaveLength(2)
})

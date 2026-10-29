import { fireEvent, render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import { expect, it, vi } from "vitest"
import type { Judgement } from "../lib/judgements"
import { JudgementCallsPanel } from "./JudgementCallsPanel"

const judgement: Judgement = {
  id: "j-1", case_id: "case-a", subject_type: "statement_period", subject_id: "p-1", source_document_id: "d-1",
  statement_period_id: "p-1", evidence_file_id: null, filename: "08 BBVA AGO 2023.pdf",
  rule_id: "L8.unprinted_opening", rule_label: "Opening balance worked back from the closing", rule_source: "fin-queue3 L8",
  target_key: "opening_balance", origin: "processor", strength: "inferred",
  summary: "Opening 12,340.00 is not printed in these pages.", page: 2, category: "balance",
  category_label: "Balance or opening worked out", status: "open", resolved_by: null, resolved_at: null,
  resolution_reason: null, adjudication_id: null,
}
vi.mock("../hooks/use-financial-access", () => ({ useFinancialAccess: () => ({ canEdit: true }) }))
vi.mock("../hooks/use-judgements", async (original) => ({
  ...(await original<typeof import("../hooks/use-judgements")>()),
  useJudgementCounts: () => ({
    data: { case: { total: 404, inferred: 198, open: 403, confirmed: 1 }, statements: {}, periods: {}, accounts: {}, rules: [{ rule_id: "L8.unprinted_opening", label: "Opening worked back", total: 37 }] },
  }),
  useJudgementSearch: () => ({
    isPending: false, isError: false, isFetching: false,
    data: {
      items: [judgement], total: 1, offset: 0,
      facets: { status: { all: 404, open: 403, confirmed: 1 }, category: { all: 404, balance: 37 }, strength: { all: 404, inferred: 198, proved: 206 }, origin: { all: 404, processor: 404 } },
      categories: [{ key: "balance", label: "Balance or opening worked out" }],
      rules: [["L8.unprinted_opening", "Opening worked back", "balance"]], accounts: [], files: [],
    },
  }),
}))
vi.mock("./ImportedStatementDetails", () => ({ ImportedStatementDetails: () => null }))
vi.mock("./SavedStatementPayments", () => ({ SavedStatementPayments: () => null }))
vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn(async () => ({ case: [], all_cases: [] })) }))

it("keeps search, every filter row with counts, rule types under a type, the raw rule id and processor rules", () => {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={["/?jType=balance"]}>
        <JudgementCallsPanel caseId="case-a" />
      </MemoryRouter>
    </QueryClientProvider>
  )
  expect(screen.getByRole("heading", { name: /404 on this case\.\s*You've checked 1\. Start with the guesses\./ })).toBeTruthy()
  expect(screen.getByRole("searchbox", { name: "Search judgement calls" })).toBeTruthy()
  for (const group of ["Show", "Type", "Strength", "Made by"]) expect(screen.getByRole("group", { name: group })).toBeTruthy()
  expect(screen.getByRole("button", { name: /Inferred \(198\)/ })).toBeTruthy()
  expect(screen.getByRole("button", { name: /Balance or opening worked out \(37\)/ }).getAttribute("aria-pressed")).toBe("true")
  expect(screen.getByLabelText("Rule types in this type").textContent).toContain("Opening worked back 37")
  // a single call in its statement opens by default and shows the raw rule id
  fireEvent.click(screen.getByRole("button", { name: "Technical details" }))
  expect(screen.getByText(/Rule L8\.unprinted_opening/)).toBeTruthy()
  expect(screen.getByRole("button", { name: "Looks right" })).toBeTruthy()
  const rules = screen.getByRole("button", { name: /Processor rules/ })
  expect(rules.getAttribute("aria-expanded")).toBe("false")
  fireEvent.click(rules)
  expect(rules.getAttribute("aria-expanded")).toBe("true")
})

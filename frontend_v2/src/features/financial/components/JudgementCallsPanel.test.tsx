import { fireEvent, render, screen, waitFor } from "@testing-library/react"
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
  category_label: "Balance or opening worked out", priority: 1, priority_label: "Check first", status: "open", resolved_by: null, resolved_at: null,
  resolution_reason: null, adjudication_id: null,
}
const described: Judgement = {
  ...judgement, id: "j-2", source_document_id: "d-1", rule_id: "category.model", rule_label: "Category suggested by the model",
  subject_type: "transaction", subject_id: "t-1", category: "payment_category", category_label: "Category suggested by the model",
  priority: 3, priority_label: "When convenient", summary: "Category Fuel suggested by the model.",
}
vi.mock("../hooks/use-financial-access", () => ({ useFinancialAccess: () => ({ canEdit: true }) }))
vi.mock("../hooks/use-judgements", async (original) => ({
  ...(await original<typeof import("../hooks/use-judgements")>()),
  useJudgementCounts: () => ({
    data: { case: { total: 404, inferred: 198, open: 403, confirmed: 1, priority_1: 250 }, statements: {}, periods: {}, accounts: {}, rules: [{ rule_id: "L8.unprinted_opening", label: "Opening worked back", total: 37 }] },
  }),
  useJudgementSearch: () => ({
    isPending: false, isError: false, isFetching: false,
    data: {
      items: [judgement, described], total: 2, offset: 0,
      facets: { priority: { all: 403, "1": 250, "2": 100, "3": 53 }, status: { all: 404, open: 403, confirmed: 1 }, category: { all: 404, balance: 37 }, strength: { all: 404, inferred: 198, proved: 206 }, origin: { all: 404, processor: 404 } },
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
      <MemoryRouter initialEntries={["/?jType=balance&jPriority=1"]}>
        <JudgementCallsPanel caseId="case-a" />
      </MemoryRouter>
    </QueryClientProvider>
  )
  expect(screen.getByRole("heading", { name: /404 on this case\.\s*You've checked 1\.\s*Start with the 250 to check first/ })).toBeTruthy()
  expect(screen.getByRole("searchbox", { name: "Search judgement calls" })).toBeTruthy()
  for (const group of ["Show", "Type", "Strength", "Made by"]) expect(screen.getByRole("group", { name: group })).toBeTruthy()
  expect(screen.getByRole("button", { name: /Inferred \(198\)/ })).toBeTruthy()
  // Legend with counts per tier; the tier in the address is the one pressed.
  const legend = screen.getByRole("group", { name: "Priority" })
  expect(legend.textContent).toContain("Check first (250)")
  expect(legend.textContent).toContain("Check soon (100)")
  expect(legend.textContent).toContain("When convenient (53)")
  expect(screen.getByRole("button", { name: /Check first \(250\)/ }).getAttribute("aria-pressed")).toBe("true")
  // Focus first: one statement's calls are grouped within their tier, each group tinted and labelled in words.
  const groups = screen.getAllByTestId("judgement-group")
  expect(groups.map((group) => group.getAttribute("data-priority"))).toEqual(["1", "3"])
  expect(groups[0].className).toContain("border-l-4")
  expect(groups[0].textContent).toContain("Check first")
  expect(groups[1].textContent).toContain("When convenient")
  expect(screen.getByRole("button", { name: /Download these 2 calls \(CSV\)/ })).toBeTruthy()
  expect(screen.getByRole("button", { name: /Balance or opening worked out \(37\)/ }).getAttribute("aria-pressed")).toBe("true")
  expect(screen.getByLabelText("Rule types in this type").textContent).toContain("Opening worked back 37")
  // a single call in its statement opens by default and shows the raw rule id
  fireEvent.click(screen.getAllByRole("button", { name: "Technical details" })[0])
  expect(screen.getByText(/Rule L8\.unprinted_opening/)).toBeTruthy()
  expect(screen.getAllByRole("button", { name: "Looks right" }).length).toBe(2)
  const rules = screen.getByRole("button", { name: /Processor rules/ })
  expect(rules.getAttribute("aria-expanded")).toBe("false")
  fireEvent.click(rules)
  expect(rules.getAttribute("aria-expanded")).toBe("true")
})

it("shows beside each rule type how often people confirmed and corrected it across all cases", async () => {
  const { fetchAPI } = await import("@/lib/api-client")
  vi.mocked(fetchAPI).mockImplementation(async (url: string) => (String(url).includes("/judgements/rules") ? {
    case: [],
    all_cases: [{ rule_id: "L8.unprinted_opening", label: "Opening worked back", source: "fin-queue3 L8", strength: "inferred",
      open: 30, confirmed: 5, corrected: 2, total: 37 }],
  } : { case: [], all_cases: [] }) as never)
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={["/?jType=balance"]}>
        <JudgementCallsPanel caseId="case-a" />
      </MemoryRouter>
    </QueryClientProvider>
  )
  await waitFor(() => expect(screen.getByLabelText("Rule types in this type").textContent)
    .toContain("Opening worked back 37 (all cases: 5 looks right, 2 corrected)"))
})

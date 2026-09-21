import {
  render,
  screen,
  fireEvent,
  within,
  cleanup,
} from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { TrendComparisonWorkspace } from "./TrendComparisonWorkspace"
import { useFinancialDraftStore } from "../stores/financial-drafts"
import { trendRows, trendCoverage } from "../lib/trend-fixture.test-support"
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({ canEdit: true }),
}))
vi.mock("./PaymentComparison", () => ({
  PaymentComparison: ({
    ids,
    title,
    onClose,
  }: {
    ids: string[]
    title: string
    onClose: () => void
  }) => (
    <div role="dialog" aria-label={title}>
      <output>{ids.join(",")}</output>
      <button onClick={onClose}>Close comparison</button>
    </div>
  ),
}))
vi.mock("./InvestigatorFindingEditor", () => ({
  InvestigatorFindingEditor: ({
    ids,
    initial,
  }: {
    ids: string[]
    initial: { title: string; explanation: string }
  }) => (
    <div role="dialog" aria-label="Finding">
      <p>{initial.title}</p>
      <p>{initial.explanation}</p>
      <output>{ids.join(",")}</output>
    </div>
  ),
}))
afterEach(() => {
  cleanup()
  useFinancialDraftStore.setState({ drafts: {} })
})
it("explains changes, opens exact evidence and seeds a finding with periods and limitations", () => {
  render(
    <TrendComparisonWorkspace
      caseId="case"
      rows={trendRows}
      coverage={trendCoverage}
      onCoverageRetry={vi.fn()}
    />
  )
  expect(
    screen.getByRole("heading", { name: "What drove the change?" })
  ).toBeInTheDocument()
  const returns = screen.getByRole("region", {
    name: "Transfer returns with matching references",
  })
  fireEvent.click(
    within(returns).getByRole("button", { name: "View 2 supporting payments" })
  )
  expect(screen.getByRole("dialog")).toHaveTextContent("out,return")
  fireEvent.click(screen.getByRole("button", { name: "Close comparison" }))
  const recurring = screen.getByRole("region", { name: "Recurring payments" })
  fireEvent.click(
    within(recurring).getByRole("button", { name: "Record observation" })
  )
  const finding = screen.getByRole("dialog", { name: "Finding" })
  expect(finding).toHaveTextContent("Earlier: 2021-01-01 to 2021-01-31")
  expect(finding).toHaveTextContent(
    "does not by itself prove extraction completeness"
  )
  expect(finding).toHaveTextContent(
    "subscription-dec,subscription-jan,subscription-feb"
  )
})
it("shows coverage failures and refuses overlapping or unloaded periods", () => {
  const retry = vi.fn()
  const { rerender } = render(
    <TrendComparisonWorkspace
      caseId="case"
      rows={trendRows}
      coverage={{ ...trendCoverage, available: false }}
      onCoverageRetry={retry}
    />
  )
  expect(
    screen.getByText("Comparison uses incomplete records")
  ).toBeInTheDocument()
  fireEvent.click(
    screen.getByRole("button", { name: "Retry statement coverage" })
  )
  expect(retry).toHaveBeenCalled()
  fireEvent.change(screen.getByLabelText("later start"), {
    target: { value: "2021-01-20" },
  })
  expect(screen.getByRole("alert")).toHaveTextContent("cannot overlap")
  expect(
    screen.queryByRole("table", { name: "Change drivers" })
  ).not.toBeInTheDocument()
  fireEvent.click(
    screen.getByRole("button", { name: "Latest month vs previous month" })
  )
  rerender(
    <TrendComparisonWorkspace
      caseId="case"
      rows={trendRows}
      coverage={trendCoverage}
      loadedStart="2021-02-01"
      onCoverageRetry={retry}
    />
  )
  expect(screen.getByRole("alert")).toHaveTextContent("loaded date filter")
})

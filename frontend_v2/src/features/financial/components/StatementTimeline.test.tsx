import { fireEvent, render, screen } from "@testing-library/react"
import { expect, it, vi } from "vitest"
import { StatementTimeline, type CoveragePeriod } from "./StatementTimeline"
vi.mock("./StatementSourceButton", () => ({
  StatementSourceButton: ({ periodId }: { periodId: string }) => (
    <p>Source for {periodId}</p>
  ),
}))
const period = (
  id: string,
  start: string | null,
  end: string | null,
  included = true
): CoveragePeriod => ({
  period_id: id,
  source_document_id: `doc-${id}`,
  currency: "GBP",
  start,
  end,
  included,
  exclusion_reason: included ? null : "source_not_admitted",
})
it("positions dates including leap day and retains excluded overlaps as separate statements", () => {
  render(
    <StatementTimeline
      caseId="case"
      currency="GBP"
      periods={[
        period("one", "2024-02-28", "2024-02-28"),
        period("two", "2024-03-01", "2024-03-01"),
        period("held", "2024-02-28", "2024-03-01", false),
      ]}
      gaps={[{ start: "2024-02-29", end: "2024-02-29", days: 1 }]}
      overlaps={[]}
    />
  )
  const gap = screen.getByLabelText("Gap: 2024-02-29 to 2024-02-29, 1 days")
  expect(parseFloat(gap.style.width)).toBeCloseTo(100 / 3)
  expect(screen.getAllByRole("button")).toHaveLength(3)
  expect(screen.getByText("Excluded bounds")).toBeVisible()
  fireEvent.click(
    screen.getByRole("button", {
      name: "Inspect statement 2: 2024-02-28 to 2024-03-01",
    })
  )
  expect(screen.getByText("Source for held")).toBeVisible()
  expect(screen.getByText(/Excluded: source not admitted/)).toBeVisible()
})
it("does not silently place invalid, missing or another currency's dates", () => {
  render(
    <StatementTimeline
      caseId="case"
      currency="GBP"
      periods={[
        period("ok", "2026-01-01", "2026-01-31"),
        period("missing", null, null),
        period("bad", "2026-02-30", "2026-03-01"),
        period("backwards", "2026-03-02", "2026-03-01"),
        { ...period("usd", "1900-01-01", "1900-01-02"), currency: "USD" },
      ]}
      gaps={[]}
      overlaps={[]}
    />
  )
  expect(screen.getAllByRole("button")).toHaveLength(1)
  expect(
    screen.getByText(/3 periods have missing or invalid dates/)
  ).toBeVisible()
  expect(screen.queryByText("1900-01-01")).not.toBeInTheDocument()
})
it("shows unknown bounds without manufacturing a timeline", () => {
  render(
    <StatementTimeline
      caseId="case"
      currency="USD"
      periods={[{ ...period("none", null, null), currency: "USD" }]}
      gaps={[]}
      overlaps={[]}
    />
  )
  expect(screen.getByText(/Statement coverage is unknown/)).toBeVisible()
  expect(screen.queryByRole("button")).not.toBeInTheDocument()
})

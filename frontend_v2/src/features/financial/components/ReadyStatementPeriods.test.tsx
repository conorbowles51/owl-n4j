import { fireEvent, render, screen } from "@testing-library/react"
import { expect, it, vi } from "vitest"
import { ReadyStatementPeriods } from "./ReadyStatementPeriods"

const periods = Array.from({ length: 7 }, (_, index) => ({
  statement_id: `period-${index}`,
  holder: "Synthetic holder",
  institution: "Example Bank",
  account: `TEST-${index}`,
  currency: "USD",
  period_start: "2024-01-01",
  period_end: "2024-01-31",
  transaction_count: index,
  incomplete_count: 0,
  problem_count: 0,
}))

it("keeps long collections navigable and opens the chosen period after paging", () => {
  const review = vi.fn()
  const result = render(
    <ReadyStatementPeriods periods={periods} onReview={review} canEdit />
  )
  expect(
    screen.getAllByRole("button", { name: "Review and import" })
  ).toHaveLength(5)
  expect(screen.getByText("Account and balances ready to save")).toBeVisible()
  fireEvent.click(screen.getByRole("button", { name: "Next ready statements" }))
  fireEvent.click(
    screen.getAllByRole("button", { name: "Review and import" })[1]
  )
  expect(review).toHaveBeenCalledWith("period-6")
  result.rerender(
    <ReadyStatementPeriods
      periods={periods.slice(0, 1)}
      onReview={review}
      canEdit
    />
  )
  expect(screen.getByText(/TEST-0/)).toBeVisible()
  expect(
    screen.queryByRole("button", { name: "Next ready statements" })
  ).toBeNull()
})

it("offers inspection for a read-only investigator", () => {
  const review = vi.fn()
  render(
    <ReadyStatementPeriods
      periods={periods.slice(1, 2)}
      onReview={review}
      canEdit={false}
    />
  )
  expect(screen.getByText("1 payment ready to import")).toBeVisible()
  expect(screen.queryByRole("button", { name: "Review and import" })).toBeNull()
  fireEvent.click(screen.getByRole("button", { name: "Review statement" }))
  expect(review).toHaveBeenCalledWith("period-1")
})

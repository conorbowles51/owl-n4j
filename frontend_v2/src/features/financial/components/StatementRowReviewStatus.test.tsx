import { fireEvent, render, screen, within } from "@testing-library/react"
import { expect, it, vi } from "vitest"
import { StatementRowReviewStatus } from "./StatementRowReviewStatus"

const blocker = {
  kind: "reading",
  message: "Check which deposit or withdrawal column contains this payment.",
  target: { kind: "transaction_field", row_id: "row", field: "review" },
}
const props = {
  rowId: "row",
  originalIssues: [blocker.message],
  blockers: [blocker],
  localProblems: [],
  pending: false,
  assessed: true,
  reviewed: false,
  saved: false,
  saving: false,
  failed: false,
  canMarkChecked: true,
  onMarkChecked: vi.fn(),
  onInspect: vi.fn(),
}
it("shows exact original and current reasons and preserves explicit checking", () => {
  render(<StatementRowReviewStatus {...props} />)
  expect(
    screen.getByRole("region", { name: "Row review row" })
  ).toHaveTextContent(`Source reading: ${blocker.message}`)
  fireEvent.click(screen.getByRole("button", { name: "Review source reading" }))
  expect(props.onInspect).toHaveBeenCalledWith(blocker)
  fireEvent.click(
    screen.getByRole("button", { name: "Mark checked against original" })
  )
  expect(props.onMarkChecked).toHaveBeenCalledOnce()
})
it("never calls pending, failed or unavailable assessments resolved", () => {
  const { rerender } = render(
    <StatementRowReviewStatus {...props} reviewed blockers={[]} pending />
  )
  expect(screen.queryByText(/warning is resolved/)).toBeNull()
  expect(
    screen.getByRole("button", { name: "Mark checked against original" })
  ).toBeDisabled()
  rerender(
    <StatementRowReviewStatus
      {...props}
      reviewed
      blockers={[]}
      error="Synthetic checks unavailable"
    />
  )
  expect(screen.queryByText(/warning is resolved/)).toBeNull()
  expect(screen.getByText(/Synthetic checks unavailable/)).toBeVisible()
  rerender(
    <StatementRowReviewStatus
      {...props}
      reviewed
      blockers={[]}
      assessed={false}
    />
  )
  expect(screen.queryByText(/warning is resolved/)).toBeNull()
})
it("distinguishes a saved source check from unresolved current arithmetic and targets its exact field", () => {
  const current = {
    kind: "running_balance",
    message: "The running balance differs by EUR 0.01.",
    target: { kind: "transaction_field", row_id: "row", field: "balance" },
  }
  render(
    <StatementRowReviewStatus
      {...props}
      reviewed
      saved
      canMarkChecked={false}
      blockers={[current]}
    />
  )
  const panel = within(screen.getByRole("region", { name: "Row review row" }))
  expect(panel.getByText(/warning is resolved/)).toBeVisible()
  expect(panel.getByText("Row review saved to the case.")).toBeVisible()
  expect(panel.getByText(/Printed balance:/).parentElement).toHaveTextContent(
    current.message
  )
  expect(panel.queryByText(/No current row check/)).toBeNull()
  fireEvent.click(panel.getByRole("button", { name: "Review printed balance" }))
  expect(props.onInspect).toHaveBeenCalledWith(current)
})

it("does not describe an excluded source row as verified or resolved", () => {
  render(
    <StatementRowReviewStatus
      {...props}
      reviewed
      saved
      excluded
      canMarkChecked={false}
      blockers={[]}
    />
  )
  expect(screen.getByText(/exclusion does not verify/)).toBeVisible()
  expect(
    screen.queryByText(/warning is resolved|No current row check/)
  ).toBeNull()
})

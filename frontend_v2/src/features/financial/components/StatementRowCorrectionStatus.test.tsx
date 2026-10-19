import { render, screen } from "@testing-library/react"
import { expect, it } from "vitest"
import { StatementRowCorrectionStatus } from "./StatementRowCorrectionStatus"

const props = {
  rowId: "synthetic",
  original: '4726"',
  reviewed: "510.25 EUR",
  saved: true,
  saving: false,
  newer: false,
  failed: false,
  pendingChecks: false,
  checksError: false,
  canImport: false,
  problems: ["Payments do not add up to this printed balance."],
}
it("distinguishes a persisted numeric correction from an unresolved reconciliation", () => {
  render(<StatementRowCorrectionStatus {...props} />)
  expect(screen.getByText("Row correction saved to the case.")).toBeVisible()
  expect(screen.getByText("Reviewed balance: 510.25 EUR")).toBeVisible()
  expect(
    screen.getByText(/Still needs review: Payments do not add up/)
  ).toBeVisible()
  expect(
    screen.queryByText("Current statement checks allow import.")
  ).toBeNull()
  expect(screen.getByText(/Retained for comparison/)).toHaveTextContent('4726"')
})
it("does not call newer edits saved while an earlier request completes or fails", () => {
  const view = render(
    <StatementRowCorrectionStatus {...props} saved={false} saving newer />
  )
  expect(
    screen.getByText("New row edits are not included in the save in progress.")
  ).toBeVisible()
  view.rerender(
    <StatementRowCorrectionStatus {...props} saved={false} failed />
  )
  expect(screen.getByText(/Save not confirmed/)).toBeVisible()
  expect(screen.queryByText("Row correction saved to the case.")).toBeNull()
})

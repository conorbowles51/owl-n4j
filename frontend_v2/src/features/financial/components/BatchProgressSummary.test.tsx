import { render, screen, within } from "@testing-library/react"
import { expect, it, vi } from "vitest"
import { BatchProgressSummary } from "./BatchProgressSummary"
import { BatchReadyAction } from "./BatchReadyAction"
const summary = {
  total: 14,
  available: 7,
  blocked: 6,
  imported: 1,
  pending_import: 0,
  skipped: 0,
  duplicate_ignored: 0,
  assigned: 0,
  other: 0,
  available_with_payments: 0,
  available_no_activity: 7,
  available_other: 0,
}
it("keeps PDF totals separate from whole-batch exclusive review statuses", () => {
  render(
    <BatchProgressSummary
      files={Array.from({ length: 11 }, () => ({ status: "checked" }))}
      summary={summary}
      available={0}
      imported={0}
      pending={0}
      skipped={0}
      duplicates={0}
      assigned={0}
    />
  )
  expect(screen.getByText("11 of 11 files read")).toBeVisible()
  expect(screen.getByText("14 prepared statement reviews")).toBeVisible()
  for (const [label, value] of [
    ["Ready to save", "7"],
    ["Needs review before saving", "6"],
    ["Saved to Financial", "1"],
  ])
    expect(
      within(screen.getByText(label).parentElement!).getByText(value)
    ).toBeVisible()
  expect(screen.getByText(/Review reasons below may overlap/)).toBeVisible()
})
const props = {
  available: 7,
  payments: 0,
  incomplete: 0,
  summary,
  filtered: true,
  canEdit: true,
  paused: false,
  pending: false,
  accepted: false,
  onConfirm: vi.fn(),
}
it("never describes unknown zero-row readiness as confirmed no activity", () => {
  render(
    <BatchReadyAction
      {...props}
      summary={{ ...summary, available_no_activity: 0, available_other: 7 }}
    />
  )
  expect(
    screen.getByRole("button", { name: "Save 7 statements to Financial" })
  ).toBeEnabled()
  expect(
    screen.getByText(/A zero payment count alone does not confirm no activity/)
  ).toBeVisible()
  expect(screen.queryByText(/are confirmed to contain no payments/)).toBeNull()
  expect(
    screen.getByText(/including statements outside the review filter/)
  ).toBeVisible()
})
it("names both payment import and all saved statements in a mixed ready batch", () => {
  render(
    <BatchReadyAction
      {...props}
      available={3}
      payments={12}
      summary={{
        ...summary,
        available: 3,
        available_with_payments: 2,
        available_no_activity: 1,
      }}
    />
  )
  expect(
    screen.getByRole("button", {
      name: "Import 12 transactions and save 3 statements",
    })
  ).toBeEnabled()
  expect(
    screen.getByText(/1 ready statement is confirmed to contain no payments/)
  ).toBeVisible()
})
it("explains a paused save without offering an enabled no-op", () => {
  render(<BatchReadyAction {...props} paused />)
  expect(
    screen.getByRole("button", { name: "Save 7 statements to Financial" })
  ).toBeDisabled()
  expect(
    screen.getByText(/Resume batch preparation before saving/)
  ).toBeVisible()
  expect(props.onConfirm).not.toHaveBeenCalled()
})

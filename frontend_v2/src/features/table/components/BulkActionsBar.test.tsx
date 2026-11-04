import { render, screen } from "@testing-library/react"
import { expect, it } from "vitest"
import { BulkActionsBar } from "./BulkActionsBar"

const bar = (count: number) =>
  render(<BulkActionsBar count={count} onMerge={() => {}} onDelete={() => {}} onBulkEdit={() => {}} onClear={() => {}} />)

it("merges every selected entity in one step up to the limit", () => {
  bar(8)
  expect(screen.getByRole("button", { name: "Merge 8" })).toBeTruthy()
  expect(screen.queryByTestId("merge-limit")).toBeNull()
})

it("states the limit and the count left out when more are selected", () => {
  bar(30)
  expect(screen.getByRole("button", { name: "Merge 25" })).toBeTruthy()
  expect(screen.getByTestId("merge-limit").textContent).toBe("up to 25 per merge; 5 left out")
})

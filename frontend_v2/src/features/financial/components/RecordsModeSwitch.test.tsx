import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { RecordsModeSwitch } from "./RecordsModeSwitch"
import { FinancialAccessNotice } from "./FinancialAccessProvider"
import { FinancialAccessContext } from "../hooks/use-financial-access"

afterEach(cleanup)

it("switches records and pins the explanation open on click instead of hover only", () => {
  const onChange = vi.fn()
  render(<RecordsModeSwitch transactionsMode onChange={onChange} />)
  expect(screen.getByRole("button", { name: "Statement payments" })).toHaveAttribute("aria-pressed", "true")
  fireEvent.click(screen.getByRole("button", { name: "Other financial records" }))
  expect(onChange).toHaveBeenCalledWith("intelligence")
  fireEvent.click(screen.getByRole("button", { name: /^About this: Statement payments come from imported/ }))
  expect(screen.getByRole("note")).toHaveTextContent("correcting a statement payment does not change them")
})

it("shows the case access notice on the switch's own line instead of a line above it", () => {
  render(
    <FinancialAccessContext.Provider value={{ canEdit: false, canUpload: false, ready: true, error: false }}>
      <RecordsModeSwitch transactionsMode onChange={vi.fn()} aside={<FinancialAccessNotice inline />} />
    </FinancialAccessContext.Provider>
  )
  const notice = screen.getByTestId("financial-access-notice")
  expect(notice).toHaveTextContent("This case is read-only.")
  expect(notice).toHaveAttribute("role", "status")
  // One row: the notice is a sibling of the switch, not a bordered line of its own.
  expect(notice.parentElement).toBe(screen.getByRole("group", { name: "Which financial records to show" }).parentElement)
  expect(notice.className).not.toContain("border-b")
})

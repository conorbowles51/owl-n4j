import { render, screen } from "@testing-library/react"
import { expect, it } from "vitest"
import { StatementCurrencyControl } from "./StatementCurrencyControl"

it("opens and focuses the currency choice when the queue issue is the currency", () => {
  render(
    <StatementCurrencyControl currency="" disabled={false} onChange={() => {}} focus />
  )
  const select = screen.getByLabelText("Currency for this statement")
  expect(select).toHaveFocus()
  expect(select.closest("details")).toHaveAttribute("open")
})

it("leaves the choice closed otherwise", () => {
  render(<StatementCurrencyControl currency="" disabled={false} onChange={() => {}} />)
  expect(screen.getByLabelText("Currency for this statement")).not.toHaveFocus()
  expect(screen.getByLabelText("Currency for this statement").closest("details")).not.toHaveAttribute("open")
})

it("offers the proposed currency as one click, focused when the issue is the currency", () => {
  const changes: string[] = []
  render(
    <StatementCurrencyControl
      currency=""
      disabled={false}
      onChange={(value) => changes.push(value)}
      focus
      proposal={{ value: "USD", label: "the case's usual currency (175 of 175 saved statements)" }}
    />
  )
  expect(screen.getByLabelText("Proposed currency")).toHaveTextContent(
    "Proposed: USD (the case's usual currency (175 of 175 saved statements))"
  )
  const use = screen.getByRole("button", { name: "Use USD" })
  expect(use).toHaveFocus()
  use.click()
  expect(changes).toEqual(["USD"])
})

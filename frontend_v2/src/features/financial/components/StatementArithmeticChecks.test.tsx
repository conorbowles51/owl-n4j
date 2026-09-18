import { fireEvent, render, screen } from "@testing-library/react"
import { expect, it, vi } from "vitest"
import { arithmeticCheck } from "../hooks/use-statement-checks"
import { StatementArithmeticChecks } from "./StatementArithmeticChecks"

it("explains an interest difference and opens its total or contributing charge", () => {
  const onInspect = vi.fn()
  const difference = arithmeticCheck.parse({
    kind: "interest_total",
    status: "difference",
    expected_minor: "3652",
    printed_minor: "3632",
    difference_minor: "20",
    row_id: "total",
    contributing_row_ids: ["charge"],
  })
  const view = render(
    <StatementArithmeticChecks
      checks={[difference]}
      format={(v) => `$${(Number(v) / 100).toFixed(2)}`}
      onInspect={onInspect}
    />
  )
  expect(
    screen.getByText("Interest charges against printed total: needs checking")
  ).toBeInTheDocument()
  expect(
    screen.getByText("Calculated $36.52. Printed $36.32. Difference $0.20.")
  ).toBeInTheDocument()
  fireEvent.click(screen.getByRole("button", { name: "View printed value" }))
  expect(onInspect).toHaveBeenLastCalledWith("total")
  fireEvent.click(screen.getByRole("button", { name: "Check charge 1" }))
  expect(onInspect).toHaveBeenLastCalledWith("charge")
  view.rerender(
    <StatementArithmeticChecks
      checks={[
        {
          ...difference,
          status: "matches",
          expected_minor: "3632",
          difference_minor: "0",
        },
      ]}
      format={(v) => v}
      onInspect={onInspect}
    />
  )
  expect(
    screen.getByText("Interest charges against printed total: matches")
  ).toBeInTheDocument()
  expect(
    screen.queryByRole("button", { name: "Check charge 1" })
  ).not.toBeInTheDocument()
})

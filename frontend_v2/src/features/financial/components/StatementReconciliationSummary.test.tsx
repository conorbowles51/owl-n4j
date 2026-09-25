import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, expect, it } from "vitest"
import { StatementReconciliationSummary } from "./StatementReconciliationSummary"
afterEach(cleanup)
const calculation = {
  available: true,
  currency: "USD",
  balance_convention: "asset_balance",
  opening_minor: "10000000",
  credit_minor: "40000000",
  debit_minor: "10000000",
  calculated_closing_minor: "40000000",
  printed_closing_minor: "50000000",
  difference_minor: "-10000000",
}
const format = (value: string) => `${value} minor units`
it("shows the exact shortfall and replaces it with the corrected current result", () => {
  const view = render(
    <StatementReconciliationSummary calculation={calculation} format={format} />
  )
  expect(screen.getByRole("status")).toHaveTextContent(
    "10000000 minor units short of the printed closing balance"
  )
  view.rerender(
    <StatementReconciliationSummary
      calculation={calculation}
      pending
      format={format}
    />
  )
  expect(screen.getByRole("status")).toHaveTextContent(
    "Checking your current values"
  )
  expect(screen.queryByText(/short of/)).not.toBeInTheDocument()
  view.rerender(
    <StatementReconciliationSummary
      calculation={{
        ...calculation,
        difference_minor: "0",
        calculated_closing_minor: "50000000",
      }}
      format={format}
    />
  )
  expect(screen.getByRole("status")).toHaveTextContent(
    "All other statement checks must also pass"
  )
})
it("does not present incomplete arithmetic as a zero difference", () => {
  render(
    <StatementReconciliationSummary
      calculation={{
        ...calculation,
        available: false,
        calculated_closing_minor: null,
        difference_minor: null,
      }}
      format={format}
    />
  )
  expect(screen.getByRole("status")).toHaveTextContent(
    "Cannot calculate the difference yet"
  )
})
it("keeps large exact amounts and card sign explanation", () => {
  render(
    <StatementReconciliationSummary
      calculation={{
        ...calculation,
        balance_convention: "liability_owed",
        difference_minor: "9007199254740993",
      }}
      format={format}
    />
  )
  expect(screen.getByRole("status")).toHaveTextContent(
    "9007199254740993 minor units above"
  )
  expect(
    screen.getByText(/Opening amount owed \+ charges − payments/)
  ).toBeVisible()
})

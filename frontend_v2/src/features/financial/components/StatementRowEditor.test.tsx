import { fireEvent, render, screen } from "@testing-library/react"
import { expect, it, vi } from "vitest"
import { StatementRowEditor } from "./StatementRowEditor"
import { statementControlLabel } from "../lib/statement-control-label"

it.each([
  [{ total_direction: "credit" }, "Printed credit total"],
  [{ total_direction: "debit" }, "Printed debit total"],
  [{ total_scope: "fee", total_direction: "debit" }, "Printed fee total"],
  [
    { total_scope: "interest", total_direction: "debit" },
    "Printed interest total",
  ],
] as const)(
  "edits the source total separately from payment and balance fields: %s",
  (fields, label) => {
    const balance = vi.fn(),
      amount = vi.fn(),
      update = vi.fn()
    render(
      <StatementRowEditor
        caseId="synthetic"
        kind="statement_total"
        row={{
          id: "total",
          excluded: true,
          date: "",
          description: "Printed summary",
          counterparty: "",
          amount_minor: "0",
          direction: "",
          balance_minor: "0",
          reason: "",
        }}
        controlContext={{
          label: statementControlLabel("statement_total", fields),
          originalValue: "0.00",
          currency: "EUR",
          page: 3,
          row: 8,
        }}
        problems={[]}
        update={update}
        amount={amount}
        balance={balance}
        text={() => "0.00"}
        close={() => {}}
      />
    )
    const input = screen.getByRole("textbox", {
      name: `Corrected ${label.toLowerCase()}`,
    })
    expect(input).toBeEnabled()
    expect(
      screen.getByText(
        /PDF page 3, extracted row 8. Original reading: 0.00 EUR/
      )
    ).toBeVisible()
    expect(
      screen.queryByLabelText("Include this transaction")
    ).not.toBeInTheDocument()
    expect(
      screen.queryByLabelText("Corrected printed balance")
    ).not.toBeInTheDocument()
    fireEvent.change(input, { target: { value: "427.00" } })
    expect(balance).toHaveBeenCalledWith("427.00")
    expect(amount).not.toHaveBeenCalled()
    expect(update).not.toHaveBeenCalled()
    expect(screen.getByText(/Original reading: 0.00 EUR/)).toBeVisible()
  }
)

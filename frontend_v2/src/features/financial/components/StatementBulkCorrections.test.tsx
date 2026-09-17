import { fireEvent, render, screen } from "@testing-library/react"
import { expect, it, vi } from "vitest"
import { StatementBulkCorrections } from "./StatementBulkCorrections"
import {
  previewCorrections,
  type ReviewEdit,
} from "../lib/statement-bulk-correction"

const makeRow = (id: string): ReviewEdit => ({
  id,
  date: "2020-01-02",
  description: `Shop ${id}`,
  counterparty: "",
  amount_minor: "1250",
  balance_minor: "2500",
  direction: "debit",
  excluded: false,
  reason: "Earlier correction",
})
it("removes the undated marker when a printed date is supplied to selected rows", () => {
  const row = { ...makeRow("interest"), date: "", date_unprinted: true }
  const changes = previewCorrections(
    [row],
    new Set([row.id]),
    "date",
    "2020-01-20",
    "Date found in source"
  )
  expect(changes[0].after).toMatchObject({
    date: "2020-01-20",
    date_unprinted: false,
  })
  expect(row).toMatchObject({ date: "", date_unprinted: true })
})

it("previews and applies all selected pages without changing originals or replacing earlier reasons", () => {
  const rows = Array.from({ length: 75 }, (_, index) => makeRow(String(index)))
  const apply = vi.fn(),
    inspect = vi.fn()
  render(
    <StatementBulkCorrections rows={rows} apply={apply} inspect={inspect} />
  )
  fireEvent.click(screen.getByRole("button", { name: "Correct several rows" }))
  fireEvent.click(
    screen.getByRole("button", { name: "Select all 75 matching rows" })
  )
  fireEvent.change(screen.getByLabelText("Correction"), {
    target: { value: "switch" },
  })
  fireEvent.change(screen.getByLabelText("Reason for these corrections"), {
    target: { value: "Printed in the credit column" },
  })
  fireEvent.click(screen.getByRole("button", { name: "Preview corrections" }))
  expect(apply).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole("button", { name: "Next correction page" }))
  fireEvent.click(screen.getAllByRole("button", { name: "View original" })[0])
  expect(inspect).toHaveBeenCalledWith("30")
  fireEvent.click(
    screen.getByRole("button", { name: "Apply corrections to 75 rows" })
  )
  const changes = apply.mock.calls[0][0]
  expect(changes).toHaveLength(75)
  expect(changes[74].after).toMatchObject({
    direction: "credit",
    amount_minor: "1250",
    balance_minor: "2500",
    reason: "Earlier correction\nPrinted in the credit column",
  })
  expect(rows[74].direction).toBe("debit")
})

it("refuses an outdated preview and can restore an excluded row", () => {
  const row = { ...makeRow("a"), excluded: true },
    apply = vi.fn()
  const props = { rows: [row], apply, inspect: vi.fn() }
  const view = render(<StatementBulkCorrections {...props} />)
  fireEvent.click(screen.getByRole("button", { name: "Correct several rows" }))
  fireEvent.click(
    screen.getByRole("button", { name: "Select all 1 matching rows" })
  )
  fireEvent.change(screen.getByLabelText("Correction"), {
    target: { value: "include" },
  })
  fireEvent.change(screen.getByLabelText("Reason for these corrections"), {
    target: { value: "Payment checked on the source" },
  })
  fireEvent.click(screen.getByRole("button", { name: "Preview corrections" }))
  view.rerender(
    <StatementBulkCorrections
      {...props}
      rows={[{ ...row, date: "2020-01-03" }]}
    />
  )
  expect(
    screen.getByRole("button", { name: "Apply corrections to 1 rows" })
  ).toBeDisabled()
  expect(screen.getByRole("alert")).toHaveTextContent("Values changed")
  fireEvent.click(screen.getByRole("button", { name: "Preview corrections" }))
  fireEvent.click(
    screen.getByRole("button", { name: "Apply corrections to 1 rows" })
  )
  expect(apply.mock.calls[0][0][0].after).toMatchObject({
    excluded: false,
    date: "2020-01-03",
  })
})

it("validates dates, selected identities, directions and unchanged values before applying", () => {
  const rows = [makeRow("a")],
    ids = new Set(["a"])
  expect(() =>
    previewCorrections(rows, ids, "date", "2020-02-30", "reason")
  ).toThrow("valid transaction date")
  expect(() => previewCorrections(rows, ids, "date", "2020-02-29", "")).toThrow(
    "reason"
  )
  expect(() =>
    previewCorrections(rows, new Set(["missing"]), "exclude", "", "reason")
  ).toThrow("changed")
  expect(() =>
    previewCorrections(
      [{ ...rows[0], direction: "" }],
      ids,
      "switch",
      "",
      "reason"
    )
  ).toThrow("individually")
  expect(() => previewCorrections(rows, ids, "include", "", "reason")).toThrow(
    "already have"
  )
  const changes = previewCorrections(
    rows,
    ids,
    "date",
    "2020-02-29",
    "Date checked"
  )
  expect(changes[0].after.date).toBe("2020-02-29")
})

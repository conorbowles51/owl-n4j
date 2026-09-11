import { render, screen, fireEvent } from "@testing-library/react"
import { expect, it, vi } from "vitest"
import { PrintedStatementTable } from "./PrintedStatementTable"

it("retains printed headings, formatted values and empty debit or credit cells", () => {
  const onCell = vi.fn()
  const row = (id: string, index: number, values: string[]) => ({
    id,
    row_index: index,
    page_number: 1,
    table_index: 0,
    source_cells: values.map((expected_text, column_index) => ({
      expected_text,
      column_index,
      locator: { page: 1, column_index },
    })),
  })
  render(
    <PrintedStatementTable
      onCell={onCell}
      rows={[
        row("header", 0, ["Date", "Description", "Credit", "Debit", "Balance"]),
        row("payment", 1, [
          "2023-03-18",
          "Wire from GlobalTech Industries",
          "€125,000",
          "",
          "€137,450",
        ]),
        row("withdrawal", 2, [
          "2023-03-20",
          "Transfer",
          "",
          "€120,000",
          "€17,450",
        ]),
      ]}
    />
  )
  const rows = screen.getAllByRole("row")
  expect(Array.from(rows[0].children).map((cell) => cell.textContent)).toEqual([
    "Date",
    "Description",
    "Credit",
    "Debit",
    "Balance",
  ])
  expect(rows[1].children[3].textContent).toBe("")
  expect(rows[2].children[2].textContent).toBe("")
  expect(screen.queryByText("Direction")).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole("button", { name: "€125,000" }))
  expect(onCell).toHaveBeenCalledWith("payment", { page: 1, column_index: 2 })
})

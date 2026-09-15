import { render, screen, fireEvent, within } from "@testing-library/react"
import { expect, it, vi } from "vitest"
import { PrintedStatementTable } from "./PrintedStatementTable"

it("opens the requested flagged row for review without changing its source click", () => {
  const onCell = vi.fn(),
    onReviewRow = vi.fn()
  const original = {
    id: "1:0:15",
    page_number: 1,
    table_index: 0,
    row_index: 15,
    kind: "unresolved",
    issues: ["Check this row"],
    source_cells: [
      {
        column_index: 0,
        expected_text: "Printed footer",
        locator: { kind: "page_only", page: 1 },
      },
    ],
  }
  const { rerender } = render(
    <PrintedStatementTable
      rows={[original]}
      onCell={onCell}
      onReviewRow={onReviewRow}
    />
  )
  fireEvent.click(screen.getByRole("button", { name: "Review this row" }))
  expect(onReviewRow).toHaveBeenCalledWith(original.id)
  expect(onCell).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole("button", { name: "Printed footer" }))
  expect(onCell).toHaveBeenCalledWith(
    original.id,
    original.source_cells[0].locator
  )
  rerender(<PrintedStatementTable rows={[original]} onCell={onCell} />)
  expect(
    screen.queryByRole("button", { name: "Review this row" })
  ).not.toBeInTheDocument()
})

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

it("keeps separately extracted signs and description pieces clickable in the printed columns", () => {
  const onCell = vi.fn()
  const cell = (
    column_index: number,
    expected_text: string,
    x: number,
    right: number
  ) => ({
    column_index,
    expected_text,
    locator: { kind: "page_rectangle", page: 1, rect: [x, 1000, right, 9000] },
  })
  const base = { page_number: 1, table_index: 0 }
  const minus = cell(5, "-", 506000, 508000)
  const place = cell(3, "EXAMPLE CITY", 390000, 445000)
  render(
    <PrintedStatementTable
      onCell={onCell}
      rows={[
        {
          ...base,
          id: "head",
          row_index: 0,
          source_cells: [
            cell(0, "Trans Date", 90000, 120000),
            cell(1, "Item Description", 270000, 340000),
            cell(2, "Amount", 480000, 502000),
          ],
        },
        {
          ...base,
          id: "payment",
          row_index: 1,
          kind: "transaction",
          source_cells: [
            cell(0, "04/22", 90000, 110000),
            cell(1, "7412061 3P00XTMJGS", 180000, 245000),
            cell(2, "MOBILE PAYMENT-THANK YOU", 270000, 380000),
            place,
            cell(4, "114.00", 480000, 500000),
            minus,
          ],
        },
      ]}
    />
  )
  expect(
    screen.getByRole("columnheader", { name: "Unlabelled printed column" })
  ).toHaveTextContent("")
  const amountCell = screen.getByRole("cell", { name: "114.00 -" })
  fireEvent.click(within(amountCell).getByRole("button", { name: "-" }))
  expect(onCell).toHaveBeenLastCalledWith("payment", minus.locator)
  const descriptionCell = screen.getByRole("cell", {
    name: "MOBILE PAYMENT-THANK YOU EXAMPLE CITY",
  })
  fireEvent.click(
    within(descriptionCell).getByRole("button", { name: "EXAMPLE CITY" })
  )
  expect(onCell).toHaveBeenLastCalledWith("payment", place.locator)
  expect(
    screen.queryByText("Rows needing a layout check")
  ).not.toBeInTheDocument()
})

it("keeps unheaded account rows in measured positions without inventing columns or splitting OCR cells", () => {
  const onCell = vi.fn()
  const combined = {
    column_index: 2,
    expected_text: "-20.00 80. 00",
    locator: { page: 1, rect: [310000, 300000, 380000, 308000] },
  }
  render(
    <PrintedStatementTable
      onCell={onCell}
      rows={[
        {
          id: "payment",
          page_number: 1,
          table_index: 0,
          row_index: 10,
          kind: "transaction",
          fields: { statement_layout: "andrews-share-statement" },
          source_cells: [
            {
              column_index: 0,
              expected_text: "06/03",
              locator: { page: 1, rect: [15000, 300000, 35000, 308000] },
            },
            {
              column_index: 1,
              expected_text: "Withdrawal Debit Card",
              locator: { page: 1, rect: [75000, 300000, 180000, 308000] },
            },
            combined,
          ],
        },
      ]}
    />
  )
  const section = screen.getByRole("group", {
    name: "Extracted account section in printed positions",
  })
  expect(within(section).queryByRole("columnheader")).not.toBeInTheDocument()
  expect(
    screen.queryByText("Rows needing a layout check")
  ).not.toBeInTheDocument()
  const amount = within(section).getByRole("button", { name: "-20.00 80. 00" })
  fireEvent.click(amount)
  expect(onCell).toHaveBeenCalledWith("payment", combined.locator)
  expect(amount.style.gridColumn).not.toBe(
    within(section).getByRole("button", { name: "06/03" }).style.gridColumn
  )
})

it("retains unheaded source text when page positions are unavailable", () => {
  const onCell = vi.fn()
  render(
    <PrintedStatementTable
      onCell={onCell}
      rows={[
        {
          id: "unlocated",
          page_number: 1,
          table_index: 0,
          row_index: 0,
          fields: { statement_layout: "andrews-share-statement" },
          source_cells: [
            {
              column_index: 0,
              expected_text: "Unlocated original reading",
              locator: { kind: "page_only", page: 1 },
            },
          ],
        },
      ]}
    />
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Unlocated original reading" })
  )
  expect(onCell).toHaveBeenCalledWith("unlocated", {
    kind: "page_only",
    page: 1,
  })
})

import { fireEvent, render, screen, within } from "@testing-library/react"
import { beforeEach, expect, it, vi } from "vitest"
import { StatementSectionPicker } from "./StatementSectionPicker"
import { useStatementWorkspace } from "../stores/statement-workspace"
const choices = [
  {
    id: "checking",
    institution: "Example bank",
    account_reference: "1234 / Share 0040",
    account_label: "Checking",
    period_start: "2020-09-01",
    period_end: "2020-09-30",
    page_numbers: [13, 14],
  },
  {
    id: "saving",
    institution: "Example bank",
    account_reference: "1234 / Share 0000",
    account_label: "Savings",
    period_start: "2020-09-01",
    period_end: "2020-09-30",
    page_numbers: [15],
  },
  {
    id: "receipt",
    institution: "Example bank",
    account_reference: "****4321",
    document_kind: "deposit_receipt" as const,
    statement_date: "2020-10-02",
    period_start: "",
    period_end: "",
    page_numbers: [42],
  },
]
beforeEach(() => useStatementWorkspace.setState({ sectionSearches: {} }))
it("filters by all search words without changing PDF order, and selects the exact matching section", () => {
  const choose = vi.fn()
  render(
    <StatementSectionPicker
      choices={choices}
      scope="user:case:file"
      onChoose={choose}
    />
  )
  const area = screen.getByRole("region", { name: "Statements in this PDF" })
  expect(
    within(area)
      .getAllByRole("button")
      .map((b) => b.textContent)
  ).toEqual([
    expect.stringContaining("0040"),
    expect.stringContaining("0000"),
    expect.stringContaining("Deposit receipt"),
  ])
  fireEvent.change(
    screen.getByRole("searchbox", { name: "Find a statement or receipt" }),
    { target: { value: "SAVINGS 2020-09" } }
  )
  expect(screen.getByRole("status")).toHaveTextContent("1 of 3 sections")
  fireEvent.click(screen.getByRole("button", { name: /Share 0000/ }))
  expect(choose).toHaveBeenCalledWith("saving")
  expect(screen.queryByRole("button", { name: /Share 0040/ })).toBeNull()
})
it("finds a receipt by its original PDF page and offers a clear way out of an empty search", () => {
  render(
    <StatementSectionPicker
      choices={choices}
      scope="user:case:file"
      onChoose={vi.fn()}
    />
  )
  const input = screen.getByRole("searchbox")
  fireEvent.change(input, { target: { value: "receipt 42" } })
  expect(screen.getByRole("status")).toHaveTextContent("1 of 3")
  expect(
    screen.getByRole("button", { name: /Deposit receipt/ })
  ).toBeInTheDocument()
  fireEvent.change(input, { target: { value: "2030" } })
  expect(screen.getByText(/No sections match this search/)).toBeInTheDocument()
  fireEvent.click(screen.getByRole("button", { name: "Clear search" }))
  expect(screen.getByRole("status")).toHaveTextContent("3 of 3")
})
it("remembers the search when returning to a file and keeps other files and users separate", () => {
  const props = { choices, onChoose: vi.fn() }
  const { rerender } = render(
    <StatementSectionPicker {...props} scope="user:case:file-a" />
  )
  fireEvent.change(screen.getByRole("searchbox"), { target: { value: "0040" } })
  rerender(<StatementSectionPicker {...props} scope="user:case:file-b" />)
  expect(screen.getByRole("searchbox")).toHaveValue("")
  rerender(<StatementSectionPicker {...props} scope="other-user:case:file-a" />)
  expect(screen.getByRole("searchbox")).toHaveValue("")
  rerender(<StatementSectionPicker {...props} scope="user:case:file-a" />)
  expect(screen.getByRole("searchbox")).toHaveValue("0040")
})

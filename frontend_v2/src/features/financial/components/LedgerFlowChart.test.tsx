import { render, screen, fireEvent } from "@testing-library/react"
import { expect, it, vi } from "vitest"
import { LedgerFlowChart } from "./LedgerFlowChart"
import { flowBarPercent } from "../lib/flow-bar-percent"
const groups = [
  {
    id: "a",
    label: "Printed A",
    currency: "GBP",
    credits_minor: "9007199254740993",
    debits_minor: "0",
    transaction_ids: ["one"],
  },
  {
    id: "b",
    label: "Printed B",
    currency: "GBP",
    credits_minor: "0",
    debits_minor: "9007199254740992",
    transaction_ids: ["two"],
  },
  {
    id: "c",
    label: "Other currency",
    currency: "USD",
    credits_minor: "300",
    debits_minor: "0",
    transaction_ids: ["three"],
  },
]
it("keeps exact selected net values above the safe integer range and links source rows", () => {
  const source = vi.fn()
  render(
    <LedgerFlowChart groups={groups} title="Comparison" onSource={source} />
  )
  expect(screen.getByText("0.01 GBP")).toBeInTheDocument()
  fireEvent.click(
    screen.getByRole("button", { name: "Inspect chart group Printed B" })
  )
  fireEvent.click(screen.getByRole("button", { name: "Open chart posting 1" }))
  expect(source).toHaveBeenCalledWith("two")
  fireEvent.click(screen.getByLabelText("Include chart group Printed B"))
  expect(screen.queryByText("0.01 GBP")).not.toBeInTheDocument()
  expect(screen.getByText(/1 of 2 groups selected/)).toBeInTheDocument()
})
it("separates currencies and resets the old source selection", () => {
  render(
    <LedgerFlowChart groups={groups} title="Comparison" onSource={vi.fn()} />
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Inspect chart group Printed A" })
  )
  fireEvent.change(screen.getByLabelText("Comparison currency"), {
    target: { value: "USD" },
  })
  expect(
    screen.queryByRole("region", { name: "Chart contributing sources" })
  ).not.toBeInTheDocument()
  expect(screen.getByText(/1 of 1 groups selected/)).toBeInTheDocument()
  expect(screen.queryByText("0.01 GBP")).not.toBeInTheDocument()
})
it("scales only bounded bar percentages and handles zero totals", () => {
  expect(flowBarPercent("9007199254740993", 9007199254740993n)).toBe(100)
  expect(flowBarPercent("0", 0n)).toBe(0)
  expect(flowBarPercent("1", 9007199254740993n)).toBe(0)
})
it("opens all selected total contributors and keeps changes scoped to the selected currency", () => {
  const source = vi.fn()
  render(
    <LedgerFlowChart groups={groups} title="Comparison" onSource={source} />
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Inspect selected chart totals" })
  )
  expect(
    screen.getByText("Selected chart totals · 2 postings")
  ).toBeInTheDocument()
  fireEvent.click(screen.getByRole("button", { name: "Open chart posting 2" }))
  expect(source).toHaveBeenCalledWith("two")
  fireEvent.click(screen.getByLabelText("Include chart group Printed B"))
  expect(
    screen.getByText("Selected chart totals · 1 postings")
  ).toBeInTheDocument()
  expect(
    screen.queryByRole("button", { name: "Open chart posting 2" })
  ).not.toBeInTheDocument()
  fireEvent.change(screen.getByLabelText("Comparison currency"), {
    target: { value: "USD" },
  })
  expect(
    screen.queryByRole("region", { name: "Chart contributing sources" })
  ).not.toBeInTheDocument()
})

import { fireEvent, render, screen, cleanup } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { paymentFixture } from "../lib/payment-fixture.test-support"
import { useFinancialDraftStore } from "../stores/financial-drafts"
import { NearbyPaymentSearch } from "./NearbyPaymentSearch"

const read = vi.hoisted(() => vi.fn())
vi.mock("../hooks/use-ledger-transactions", () => ({
  useLedgerTransactions: read,
}))
vi.mock("./PaymentComparison", () => ({
  PaymentComparison: ({ ids }: { ids: string[] }) => (
    <p>Compared: {ids.join(",")}</p>
  ),
}))
afterEach(() => {
  cleanup()
  useFinancialDraftStore.setState({ drafts: {} })
  vi.clearAllMocks()
})
const row = {
  ...paymentFixture,
  key: "payment",
  case_id: "case",
  account_id: "account",
  ordering_date: "2024-03-01",
}

it("shows the actual account/date interval and omits statement-end substitutes", () => {
  read.mockReturnValue({
    data: {
      case_id: "case",
      total: 2,
      transactions: [
        row,
        {
          ...row,
          key: "undated",
          ordering_date_context: "statement_end_ordering_only",
        },
      ],
    },
  })
  render(<NearbyPaymentSearch caseId="case" row={row} />)
  expect(read).toHaveBeenLastCalledWith(undefined, expect.anything())
  fireEvent.click(screen.getByRole("button", { name: "Related payments" }))
  expect(read).toHaveBeenLastCalledWith("case", {
    accountId: "account",
    startDate: "2024-03-01",
    endDate: "2024-03-08",
  })
  fireEvent.change(
    screen.getByRole("combobox", { name: "Related payment days" }),
    { target: { value: "1" } }
  )
  expect(screen.getByText(/2024-03-01 to 2024-03-02/)).toBeVisible()
  expect(
    screen.getByRole("button", { name: "Compare 1 selected payments" })
  ).toBeDisabled()
})

it.each([
  { total: 2, transactions: [row] },
  { total: 1, transactions: [{ ...row, account_id: "another-account" }] },
  { total: 2, transactions: [row, row] },
])(
  "does not compare incomplete or incorrectly scoped responses",
  (response) => {
    read.mockReturnValue({ data: { case_id: "case", ...response } })
    render(<NearbyPaymentSearch caseId="case" row={row} />)
    fireEvent.click(screen.getByRole("button", { name: "Related payments" }))
    expect(screen.getByRole("alert")).toHaveTextContent(
      "could not be fully loaded"
    )
    expect(
      screen.queryByRole("button", { name: "Compare 1 selected payments" })
    ).not.toBeInTheDocument()
  }
)

it("does not offer date comparisons for an undated transaction", () => {
  read.mockReturnValue({})
  render(
    <NearbyPaymentSearch
      caseId="case"
      row={{ ...row, ordering_date_context: "statement_end_ordering_only" }}
    />
  )
  expect(screen.queryByRole("button")).not.toBeInTheDocument()
})

it("lets the investigator choose an outgoing payment and keeps it when the interval narrows", () => {
  const outgoing = {
    ...row,
    key: "outgoing",
    description: "Transfer to Cayman National Bank",
    ordering_date: "2024-03-03",
    direction: "debit",
  }
  read.mockReturnValue({
    data: { case_id: "case", total: 2, transactions: [row, outgoing] },
  })
  const view = render(<NearbyPaymentSearch caseId="case" row={row} />)
  fireEvent.click(screen.getByRole("button", { name: "Related payments" }))
  fireEvent.click(
    screen.getByRole("checkbox", { name: /Compare Transfer to Cayman/ })
  )
  fireEvent.change(
    screen.getByRole("combobox", { name: "Related payment days" }),
    { target: { value: "1" } }
  )
  expect(
    screen.getByText(/1 selected payments are outside this interval/)
  ).toBeVisible()
  fireEvent.click(
    screen.getByRole("button", { name: "Compare 2 selected payments" })
  )
  expect(screen.getByText("Compared: payment,outgoing")).toBeVisible()
  view.unmount()
  render(<NearbyPaymentSearch caseId="case" row={row} />)
  fireEvent.click(screen.getByRole("button", { name: "Related payments" }))
  expect(
    screen.getByRole("button", { name: "Compare 2 selected payments" })
  ).toBeEnabled()
})

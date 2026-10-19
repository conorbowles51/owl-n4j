import { render, screen, fireEvent, cleanup } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { MoneyConnections } from "./InvestigatorFollowMoney"
import { paymentFixture } from "../lib/payment-fixture.test-support"
import type { LedgerTransaction } from "../api"
afterEach(cleanup)
it("separates unnamed transaction descriptions from named counterparties and opens exact groups", () => {
  const make = (
    key: string,
    description: string,
    direction = "debit",
    to_name = ""
  ): LedgerTransaction => ({
    ...paymentFixture,
    key,
    description,
    direction,
    from_name: direction === "debit" ? "Owner" : "",
    to_name: direction === "debit" ? to_name : "Owner",
    currency: "USD",
    amount_minor: "1305000",
  })
  const rows = [
    make("rent", "W01 TRASPASO A TERCEROS RENTA 21 BMRCASH"),
    make("returned", "T22 SPID DEVUELTOBANORTE Ref. 1", "credit"),
    make("tax", "C20 I.S.R. RETENIDO"),
    make("tax-fee", "C50 IVA COM SDO INFERIOR MIN 16%"),
    make(
      "intercam",
      "P14 INTERCAM BANCO SA IB REF:123 CIE:123",
      "debit",
      "INTERCAM BANCO SA IB"
    ),
  ]
  const onOpen = vi.fn()
  render(<MoneyConnections rows={rows} onOpen={onOpen} />)
  expect(screen.queryByText("Name not recorded")).not.toBeInTheDocument()
  expect(
    screen.getByText("4 payments without an identified counterparty")
  ).toBeInTheDocument()
  expect(
    screen.getByRole("button", { name: /INTERCAM BANCO/ })
  ).toBeInTheDocument()
  fireEvent.click(screen.getByRole("button", { name: /Returned transfers/ }))
  expect(onOpen).toHaveBeenLastCalledWith(["returned"], "Returned transfers")
  fireEvent.click(
    screen.getByRole("button", { name: /Transfers to third parties/ })
  )
  expect(onOpen).toHaveBeenLastCalledWith(
    ["rent"],
    "Transfers to third parties"
  )
  fireEvent.click(screen.getByRole("button", { name: /Tax entries/ }))
  expect(onOpen).toHaveBeenLastCalledWith(["tax", "tax-fee"], "Tax entries")
})
it("honours an explicit name clear and keeps currencies separate", () => {
  const row = {
    ...paymentFixture,
    from_name: "",
    label_sources: {
      from_name: { source: "investigator", explanation: "Cleared" },
    },
    amount_minor: "100",
  } as LedgerTransaction
  render(
    <MoneyConnections
      rows={[
        row,
        { ...row, key: "usd", currency: "USD", from_name: "Someone" },
      ]}
      onOpen={vi.fn()}
    />
  )
  expect(screen.getByText("Name cleared during review")).toBeInTheDocument()
  fireEvent.change(
    screen.getByLabelText("Connection currency and account type"),
    { target: { value: "USD:bank" } }
  )
  expect(
    screen.queryByText("Name cleared during review")
  ).not.toBeInTheDocument()
})

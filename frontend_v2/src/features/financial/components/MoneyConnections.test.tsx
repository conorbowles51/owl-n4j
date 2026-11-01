import { render, screen, fireEvent, cleanup } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { MoneyConnections } from "./InvestigatorFollowMoney"
import { paymentFixture } from "../lib/payment-fixture.test-support"
import type { LedgerTransaction } from "../api"
afterEach(cleanup)
it("separates unnamed transaction descriptions from named counterparties and opens exact groups", async () => {
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
  await screen.findByText("4 payments without an identified counterparty")
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
it("honours an explicit name clear and keeps currencies separate", async () => {
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
  expect(await screen.findByText("Name cleared during review")).toBeInTheDocument()
  fireEvent.change(
    screen.getByLabelText("Connection currency and account type"),
    { target: { value: "USD:bank" } }
  )
  expect(
    screen.queryByText("Name cleared during review")
  ).not.toBeInTheDocument()
})

it("says it is grouping the payments until its figures are worked out, and again for a new row list", async () => {
  const rows: LedgerTransaction[] = [
    { ...paymentFixture, key: "a", direction: "debit", from_name: "Owner", to_name: "Shop", currency: "USD", amount_minor: "100" },
    { ...paymentFixture, key: "b", direction: "credit", from_name: "Payer", to_name: "Owner", currency: "USD", amount_minor: "250" },
  ]
  const view = render(<MoneyConnections rows={rows} onOpen={vi.fn()} />)
  // The render that first shows the payments does not group them; the panel says so.
  expect(screen.getByRole("status")).toHaveTextContent("Grouping 2 payments by name and account…")
  expect(screen.queryByRole("button", { name: /Payer|Shop/ })).not.toBeInTheDocument()
  expect(await screen.findAllByRole("button", { name: /Payer|Shop/ })).not.toHaveLength(0)
  expect(screen.queryByText(/Grouping/)).not.toBeInTheDocument()
  // A changed row list (e.g. after a correction) never shows the previous figures as its own.
  view.rerender(<MoneyConnections rows={[rows[0]]} onOpen={vi.fn()} />)
  expect(screen.getByRole("status")).toHaveTextContent("Grouping 1 payment by name and account…")
  expect(screen.queryByRole("button", { name: /Payer/ })).not.toBeInTheDocument()
  expect(await screen.findAllByRole("button", { name: /Shop/ })).not.toHaveLength(0)
  expect(screen.queryByRole("button", { name: /Payer/ })).not.toBeInTheDocument()
})

it("keeps the chosen currency group and page of names when the row list changes", async () => {
  const usd = Array.from({ length: 8 }, (_, i): LedgerTransaction => ({
    ...paymentFixture, key: `usd-${i}`, direction: "debit", from_name: "Owner", to_name: `Shop ${i}`, currency: "USD", amount_minor: "100",
  }))
  const eur: LedgerTransaction = { ...paymentFixture, key: "eur", direction: "debit", from_name: "Owner", to_name: "Café", currency: "EUR", amount_minor: "100" }
  const rows = [eur, ...usd]
  const view = render(<MoneyConnections rows={rows} onOpen={vi.fn()} />)
  fireEvent.change(await screen.findByLabelText("Connection currency and account type"), { target: { value: "USD:bank" } })
  fireEvent.click(screen.getByRole("button", { name: "Next names" }))
  expect(screen.getByText(/7 to 8 of 8 names/)).toBeInTheDocument()
  // A refetch after a correction gives a new row list with the same payments.
  view.rerender(<MoneyConnections rows={[...rows]} onOpen={vi.fn()} />)
  expect(await screen.findByText(/7 to 8 of 8 names/)).toBeInTheDocument()
  expect(screen.getByLabelText("Connection currency and account type")).toHaveValue("USD:bank")
})

it("says the grouping failed, shows no figures, and offers to try again, never sitting on 'Grouping…'", async () => {
  const panels = await import("../lib/overview-panels")
  const spy = vi.spyOn(panels, "connectionGroupsInSteps").mockRejectedValueOnce(new Error("out of memory"))
  const rows: LedgerTransaction[] = [
    { ...paymentFixture, key: "a", direction: "debit", from_name: "Owner", to_name: "Shop", currency: "USD", amount_minor: "100" },
  ]
  render(<MoneyConnections rows={rows} onOpen={vi.fn()} />)
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Grouping 1 payment by name and account failed: the browser ran out of working space for this many payments (it said: out of memory). No figures are shown for this panel."
  )
  expect(screen.queryByRole("button", { name: /Shop/ })).not.toBeInTheDocument()
  spy.mockRestore()
  fireEvent.click(screen.getByRole("button", { name: "Try again" }))
  expect(await screen.findAllByRole("button", { name: /Shop/ })).not.toHaveLength(0)
  expect(screen.queryByRole("alert")).not.toBeInTheDocument()
})

it("words the browser running out of room plainly, keeping its own text in brackets", async () => {
  const panels = await import("../lib/overview-panels")
  const spy = vi.spyOn(panels, "connectionGroupsInSteps").mockRejectedValueOnce(new RangeError("Maximum call stack size exceeded"))
  const rows: LedgerTransaction[] = [
    { ...paymentFixture, key: "a", direction: "debit", from_name: "Owner", to_name: "Shop", currency: "USD", amount_minor: "100" },
  ]
  render(<MoneyConnections rows={rows} onOpen={vi.fn()} />)
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Grouping 1 payment by name and account failed: the browser ran out of working space for this many payments (it said: Maximum call stack size exceeded). No figures are shown for this panel."
  )
  spy.mockRestore()
})

it("groups a new row list after a failure without waiting for Try again, and never shows the old failure for it", async () => {
  const panels = await import("../lib/overview-panels")
  const spy = vi.spyOn(panels, "connectionGroupsInSteps").mockRejectedValueOnce(new Error("out of memory"))
  const rows: LedgerTransaction[] = [
    { ...paymentFixture, key: "a", direction: "debit", from_name: "Owner", to_name: "Shop", currency: "USD", amount_minor: "100" },
  ]
  const view = render(<MoneyConnections rows={rows} onOpen={vi.fn()} />)
  expect(await screen.findByRole("alert")).toHaveTextContent(/failed/)
  spy.mockRestore()
  // A refetch (e.g. after a correction) gives a new row list: it is grouped at once.
  view.rerender(<MoneyConnections rows={[...rows]} onOpen={vi.fn()} />)
  expect(await screen.findAllByRole("button", { name: /Shop/ })).not.toHaveLength(0)
  expect(screen.queryByRole("alert")).not.toBeInTheDocument()
})

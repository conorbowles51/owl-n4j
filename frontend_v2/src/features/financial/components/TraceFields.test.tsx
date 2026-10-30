import { fireEvent, render, screen } from "@testing-library/react"
import { expect, it, vi } from "vitest"
import { TraceAssetFields } from "./TraceAssetFields"
import {
  TraceAttributionFields,
  type DraftAttribution,
} from "./TraceAttributionFields"

// The parent stores the list and re-renders later. Under load a second field
// can be edited before that re-render; each edit must still apply to the list
// as stored, not to the list of the last render. When each edit rebuilt the
// list from the last render, the scenario was submitted with the deposit,
// claim and amount blank and only the attribution basis kept.
function applied<T>(calls: unknown[][], initial: T): T {
  return calls.reduce<T>(
    (current, [update]) =>
      typeof update === "function"
        ? (update as (value: T) => T)(current)
        : (update as T),
    initial
  )
}

it("keeps every attribution field edited before the next render", () => {
  const blank: DraftAttribution[] = [
    { transaction_id: "", claim_id: "", amount_input: "", basis: "" },
  ]
  const onChange = vi.fn()
  render(
    <TraceAttributionFields
      currency="GBP"
      credits={[{ id: "row", label: "Deposit" }]}
      value={blank}
      onChange={onChange}
    />
  )
  for (const [label, value] of [
    ["Attributed deposit", "row"],
    ["Claim label", "Claim"],
    ["Attributed amount (GBP)", "0.50"],
    ["Attribution basis", "Explicit attribution"],
  ])
    fireEvent.change(screen.getByLabelText(label), { target: { value } })
  expect(applied(onChange.mock.calls, blank)).toEqual([
    {
      transaction_id: "row",
      claim_id: "Claim",
      amount_input: "0.50",
      basis: "Explicit attribution",
    },
  ])
})

it("keeps every asset-use field edited before the next render", () => {
  const blank = [{ transaction_id: "", asset_label: "", basis: "" }]
  const onChange = vi.fn()
  render(
    <TraceAssetFields
      value={blank}
      onChange={onChange}
      withdrawals={[{ id: "debit", label: "Withdrawal" }]}
    />
  )
  fireEvent.change(screen.getByLabelText("Asset withdrawal 1"), {
    target: { value: "debit" },
  })
  fireEvent.change(screen.getByLabelText("Asset description 1"), {
    target: { value: "Car" },
  })
  fireEvent.change(screen.getByLabelText("Asset basis 1"), {
    target: { value: "Invoice" },
  })
  expect(applied(onChange.mock.calls, blank)).toEqual([
    { transaction_id: "debit", asset_label: "Car", basis: "Invoice" },
  ])
})

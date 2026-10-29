import { describe, expect, it } from "vitest"
import type { LedgerTransaction } from "../api"
import { unidentifiedPayment } from "./unidentified-payments"

const credit = (reason: string) =>
  ({
    key: reason,
    description: "EXAMPLE",
    direction: "credit",
    account_holder: "Our Co",
    from_name: "",
    to_name: "Our Co",
    label_sources: {
      from_name: { source: "missing", reason, rule: "returned-transfer" },
    },
  }) as unknown as LedgerTransaction

describe("unidentifiedPayment", () => {
  it("groups by the stated reason, not the rule, so different reasons are never totalled together", () => {
    const refund = unidentifiedPayment(credit("Refund of a bill payment"))
    const returned = unidentifiedPayment(credit("Returned transfer"))
    expect(refund?.label).toBe("Refund of a bill payment")
    expect(refund?.kind).not.toBe(returned?.kind)
  })
})

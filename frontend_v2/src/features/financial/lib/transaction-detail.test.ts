import { expect, it } from "vitest"
import { transactionDetail } from "./transaction-detail"
import { paymentFixture } from "./payment-fixture.test-support"

it("retains inference origins through the source and edit response validator", () => {
  const detail = {
    ...paymentFixture,
    category: "Shopping",
    balance_status: "not_printed",
    label_sources: {
      category: {
        source: "description",
        explanation: "Merchant descriptor",
        rule: "merchant",
        version: "description-labels/1",
      },
    },
  }
  expect(transactionDetail.parse(detail)).toMatchObject(detail)
  expect(
    transactionDetail.safeParse({ ...detail, balance_status: "calculated" })
      .success
  ).toBe(false)
})

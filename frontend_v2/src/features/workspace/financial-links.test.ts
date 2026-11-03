import { expect, it } from "vitest"
import { WORKSPACE_LINK_TYPES, DOSSIER_LINK_TYPES } from "@/generated/link-types"
import { FINANCIAL_LINK_TYPES, financialLinkHref, isFinancialLinkType } from "./financial-links"

it("matches the backend registry and opens a payment on the Financial page", () => {
  for (const type of FINANCIAL_LINK_TYPES) {
    expect(WORKSPACE_LINK_TYPES as readonly string[]).toContain(type)
    expect(DOSSIER_LINK_TYPES as readonly string[]).toContain(type)
  }
  expect(isFinancialLinkType("evidence")).toBe(false)
  expect(financialLinkHref("c1", "financial_transaction", "t1")).toBe("/cases/c1/financial?view=transactions&payment=t1")
  expect(financialLinkHref("c1", "financial_account", "a1")).toBe("/cases/c1/financial?view=statements&accounts=1")
})

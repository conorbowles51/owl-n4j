import { paymentPath } from "@/lib/citations"

/** Money a workspace entry, dossier or pin can hold (backend: postgres/link_types.py FINANCIAL_TYPES). */
export const FINANCIAL_LINK_TYPES = ["financial_account", "financial_party", "financial_transaction"] as const
export type FinancialLinkType = (typeof FINANCIAL_LINK_TYPES)[number]

export function isFinancialLinkType(value: string): value is FinancialLinkType {
  return (FINANCIAL_LINK_TYPES as readonly string[]).includes(value)
}

/**
 * Where a money link opens: a payment on the Financial page at its statement page; an account or a party on the
 * Financial page's account review, the screen that lists accounts and their holders (it has no per-account route).
 */
export function financialLinkHref(caseId: string, type: FinancialLinkType, targetId: string) {
  if (type === "financial_transaction") return paymentPath(caseId, targetId)
  return `/cases/${encodeURIComponent(caseId)}/financial?${new URLSearchParams({ view: "statements", accounts: "1" })}`
}

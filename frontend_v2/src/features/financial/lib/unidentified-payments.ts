import type { LedgerTransaction } from "../api"
import { party } from "./transaction-analysis"

/** Context for an unnamed payment, never a replacement counterparty identity. */
export function unidentifiedPayment(row: LedgerTransaction) {
  const side = row.direction === "credit" ? "from" : "to"
  if (!party(row, side).key.startsWith("unknown:")) return null
  if (
    row.label_sources?.[side === "from" ? "from_name" : "to_name"]?.source ===
    "investigator"
  )
    return {
      kind: "cleared",
      label: "Name cleared during review",
      reason:
        "An investigator left this name blank. Open the payment to review or add a name.",
    }
  const description = (row.description || "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toUpperCase()
  if (
    row.direction === "credit" &&
    /\b(?:SPID|SPEI)\s+DEVUELTO/.test(description)
  )
    return {
      kind: "returned",
      label: "Returned transfers",
      reason:
        "The description records a returned transfer. It does not name the original beneficiary; compare its reference with the outgoing payment.",
    }
  if (/\b(?:I\.?S\.?R\.?\s+RETENIDO|IVA\s+COMISION)\b/.test(description))
    return {
      kind: "tax",
      label: "Tax entries",
      reason:
        "The description identifies tax withheld or tax on a commission, without a named recipient.",
    }
  if (/\bORDEN DE PAGO EXTRANJERO\b/.test(description))
    return {
      kind: "foreign",
      label: "Foreign payment orders",
      reason:
        "The description records a foreign payment order. Open its reference and original statement to identify the counterparty.",
    }
  if (/\bTRASPASO A TERCEROS\b/.test(description))
    return {
      kind: "third-party",
      label: "Transfers to third parties",
      reason:
        "The description records a transfer to a third party, without naming the recipient. Its payment wording and reference remain available.",
    }
  if (/\b(?:SPID|SPEI)\s+ENVIADO\b/.test(description))
    return {
      kind: "sent",
      label: "Bank transfers with no named recipient",
      reason:
        "The description identifies the transfer route or bank, but no beneficiary name. A bank name alone is not treated as the recipient.",
    }
  if (
    row.account_type === "credit_card" &&
    row.direction === "credit" &&
    /(?:MOBILE|ONLINE|AUTOMATIC|AUTOPAY|ELECTRONIC)\s*(?:PYMT|PMT|PAYMENT)/.test(
      description
    )
  )
    return {
      kind: "card-payment",
      label: "Card payments with no named funding account",
      reason:
        "The payment reduces card debt. The description does not identify the person or account that funded it.",
    }
  return {
    kind: "unidentified",
    label: "Other payments with no identified name",
    reason:
      "No counterparty name is currently recorded. Open the payment to check its description and statement, or add a name.",
  }
}

export function unidentifiedGroups(rows: LedgerTransaction[]) {
  const groups = new Map<
    string,
    NonNullable<ReturnType<typeof unidentifiedPayment>> & {
      direction: string
      rows: LedgerTransaction[]
    }
  >()
  for (const row of rows) {
    const context = unidentifiedPayment(row)
    if (!context) continue
    const key = `${row.direction}:${context.kind}`
    const group = groups.get(key) ?? {
      ...context,
      direction: row.direction,
      rows: [],
    }
    group.rows.push(row)
    groups.set(key, group)
  }
  return [...groups.values()]
}

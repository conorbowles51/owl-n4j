import type { z } from "zod"
import type { candidateAccounts } from "./candidate-contract"
import type { LedgerQueryParams } from "../hooks/use-ledger-transactions"
import { bankKey, selectedAccountIds } from "./account-selection"
import { holderKey } from "./account-holder"

type DirectoryAccount = z.infer<typeof candidateAccounts>["items"][number]
export type KnownPaymentAccount = {
  id: string
  label: string
  institution: string | null
  /** Empty when no account or saved period records a currency. */
  currency: string
  accountType: string | null
  periods: NonNullable<DirectoryAccount["statement_periods"]>
}
export const knownAccountGroup = (account: KnownPaymentAccount) =>
  `${account.currency}:${account.accountType === "credit_card" ? "card" : account.accountType ? "bank" : "unknown"}`

/** Registered account context only. No payment, amount, or quiet-month inference. */
export function knownPaymentAccounts(
  items: DirectoryAccount[],
  scope: LedgerQueryParams,
  sourceIds?: string[]
) {
  const families = new Map<string, DirectoryAccount[]>()
  for (const item of items) {
    const id = item.canonical_id || item.id
    families.set(id, [...(families.get(id) ?? []), item])
  }
  const ids = selectedAccountIds(scope)
  const holders = (scope.accountHolders ?? []).filter((value) => !value.startsWith("bank:"))
  const banks = (scope.accountHolders ?? []).filter((value) => value.startsWith("bank:"))
  const sources = sourceIds ?? (scope.sourceDocumentId ? [scope.sourceDocumentId] : undefined)
  const accounts: KnownPaymentAccount[] = []
  const unknownDateAccounts: { id: string; currencies: string[] }[] = []
  for (const [id, family] of families) {
    const canonical = family.find((item) => item.id === id) ?? family[0]
    const institution = canonical.institution || family.find((item) => item.institution)?.institution || null
    if (ids.length && !family.some((item) => ids.includes(item.id) || ids.includes(item.canonical_id || item.id))) continue
    if (banks.length && !banks.includes(`bank:${bankKey(institution)}`)) continue
    if (holders.length && !family.some((item) =>
      holders.includes(holderKey(item.holder || "")) ||
      (item.party && holders.includes(`party:${item.party.id}`)) ||
      item.holder_parties.some((party) => holders.includes(`party:${party.id}`))
    )) continue
    const allPeriods = [...new Map(family.flatMap((item) => item.statement_periods ?? []).map((period) => [period.id, period])).values()]
    const sourcePeriods = sources ? allPeriods.filter((period) => sources.includes(period.source_document_id)) : allPeriods
    if (sources && !sourcePeriods.length) continue
    const dated = sourcePeriods.filter((period) => period.start && period.end && period.start <= period.end)
    const hasDates = !!scope.startDate || !!scope.endDate
    const periods = hasDates ? dated.filter((period) =>
      (!scope.startDate || period.end! >= scope.startDate) &&
      (!scope.endDate || period.start! <= scope.endDate)
    ) : sourcePeriods
    if (hasDates && !periods.length) {
      if (!dated.length || dated.length < sourcePeriods.length) unknownDateAccounts.push({
        id,
        currencies: [...new Set([...sourcePeriods.map((period) => period.currency), ...family.map((item) => item.currency)].filter((value): value is string => !!value))],
      })
      continue
    }
    const currencies = new Set(periods.map((period) => period.currency).filter(Boolean))
    if (!hasDates && !sources) for (const item of family) if (item.currency) currencies.add(item.currency)
    // Preserve the known identity in counts without inventing a denomination.
    if (!currencies.size) currencies.add("")
    const accountType = canonical.account_type || family.find((item) => item.account_type)?.account_type || null
    const label = [institution || "Bank not identified", canonical.identifier || family.find((item) => item.identifier)?.identifier || "Account number not recorded", canonical.holder || family.find((item) => item.holder)?.holder].filter(Boolean).join(" · ")
    for (const currency of currencies) accounts.push({
      id, label, institution, currency, accountType,
      periods: periods.filter((period) => period.currency === currency),
    })
  }
  return { accounts, unknownDates: unknownDateAccounts.length, unknownDateAccounts }
}

import type { LedgerTransaction } from "../api"
import { paymentDay, paymentGroup, minorAmount } from "./investigator-workspace"

export type PartySide = "from" | "to"
export type FlowKind = "" | "incoming" | "outgoing" | "internal"
export interface AnalysisFilters {
  fromNames: string[]
  toNames: string[]
  perspectiveNames: string[]
  analysisGroup: string
  analysisPeriod: string
  analysisDirection: "" | "credit" | "debit"
  analysisCategories: string[]
  flowParty: string
  flowKind: FlowKind
}
export const emptyAnalysisFilters: AnalysisFilters = {
  fromNames: [],
  toNames: [],
  perspectiveNames: [],
  analysisGroup: "",
  analysisPeriod: "",
  analysisDirection: "",
  analysisCategories: [],
  flowParty: "",
  flowKind: "",
}
export function party(row: LedgerTransaction, side: PartySide) {
  const own =
    side === "from" ? row.direction === "debit" : row.direction === "credit"
  const value =
    (side === "from" ? row.from_name : row.to_name) ??
    (own
      ? row.account_holder || row.account_label || row.account_id
      : row.counterparty_raw)
  const name = (value || "").trim().replace(/\s+/g, " ")
  const linked = !own ? row.counterparty_link : null
  return {
    key: linked
      ? `identity:${linked.kind}:${linked.id}:${encodeURIComponent(name)}`
      : name
        ? `name:${name}`
        : `unknown:${side}`,
    name: name || "Not identified",
    suggested:
      row.label_sources?.[side === "from" ? "from_name" : "to_name"]?.source ===
      "description",
  }
}
export function partyName(key: string) {
  if (key.startsWith("identity:")) {
    try {
      return (
        decodeURIComponent(key.split(":").slice(3).join(":")) ||
        "Not identified"
      )
    } catch {
      return "Not identified"
    }
  }
  return key.startsWith("name:") ? key.slice(5) : "Not identified"
}
export function amountGroupName(group: string) {
  const [currency, kind] = group.split(":")
  return `${currency} · ${kind === "card" ? "Credit cards" : "Bank accounts"}`
}
export function amountOf(row: LedgerTransaction) {
  const amount = minorAmount(row.amount_minor)
  return amount !== null &&
    amount >= 0n &&
    ["credit", "debit"].includes(row.direction)
    ? amount
    : null
}
export function flowKind(
  row: LedgerTransaction,
  selection: ReadonlySet<string>
): FlowKind {
  const from = selection.has(party(row, "from").key),
    to = selection.has(party(row, "to").key)
  return from && to ? "internal" : from ? "outgoing" : to ? "incoming" : ""
}
export function filterAnalysis(
  rows: LedgerTransaction[],
  filters: AnalysisFilters,
  omit?: "from" | "to" | "perspective" | "drill"
) {
  const from = new Set(filters.fromNames),
    to = new Set(filters.toNames),
    perspective = new Set(filters.perspectiveNames)
  const categories = new Set(filters.analysisCategories)
  return rows.filter((row) => {
    if (
      omit !== "drill" &&
      filters.analysisDirection &&
      row.direction !== filters.analysisDirection
    )
      return false
    if (filters.analysisGroup && paymentGroup(row) !== filters.analysisGroup)
      return false
    if (
      omit !== "drill" &&
      filters.analysisPeriod &&
      (filters.analysisPeriod === "undated"
        ? paymentDay(row) !== null
        : paymentDay(row)?.slice(0, 7) !== filters.analysisPeriod)
    )
      return false
    if (
      omit !== "drill" &&
      categories.size &&
      !categories.has(row.category || "Uncategorized")
    )
      return false
    if (omit !== "from" && from.size && !from.has(party(row, "from").key))
      return false
    if (omit !== "to" && to.size && !to.has(party(row, "to").key)) return false
    const kind = flowKind(row, perspective)
    if (omit !== "perspective" && perspective.size && !kind) return false
    if (
      omit !== "drill" &&
      omit !== "perspective" &&
      filters.flowKind &&
      kind !== filters.flowKind
    )
      return false
    if (
      omit !== "drill" &&
      omit !== "perspective" &&
      filters.flowParty &&
      (!kind ||
        kind === "internal" ||
        party(row, kind === "incoming" ? "from" : "to").key !==
          filters.flowParty)
    )
      return false
    return true
  })
}
export interface PartySummary {
  key: string
  name: string
  count: number
  fromCount: number
  toCount: number
  suggested: number
  amounts: Map<string, bigint>
}
export function partySummaries(
  rows: LedgerTransaction[],
  side?: PartySide
): PartySummary[] {
  const result = new Map<string, PartySummary>()
  for (const row of rows) {
    const from = party(row, "from"),
      to = party(row, "to")
    const targets = side
      ? [party(row, side)]
      : [...new Map([from, to].map((p) => [p.key, p])).values()]
    for (const p of targets) {
      const entry = result.get(p.key) ?? {
        ...p,
        count: 0,
        fromCount: 0,
        toCount: 0,
        suggested: 0,
        amounts: new Map<string, bigint>(),
      }
      entry.count++
      entry.fromCount += Number(from.key === p.key)
      entry.toCount += Number(to.key === p.key)
      entry.suggested += Number(p.suggested)
      const value = amountOf(row)
      if (value !== null)
        entry.amounts.set(
          paymentGroup(row),
          (entry.amounts.get(paymentGroup(row)) ?? 0n) + value
        )
      result.set(p.key, entry)
    }
  }
  return [...result.values()]
}
export interface FlowTotal {
  group: string
  incoming: bigint
  outgoing: bigint
  internal: bigint
  incomingCount: number
  outgoingCount: number
  internalCount: number
}
export interface CounterpartyFlow {
  key: string
  name: string
  incoming: bigint
  outgoing: bigint
  count: number
}
export function perspectiveSummary(rows: LedgerTransaction[], names: string[]) {
  const selected = new Set(names),
    totals = new Map<string, FlowTotal>()
  const counterparties = new Map<string, Map<string, CounterpartyFlow>>()
  for (const row of rows) {
    const kind = flowKind(row, selected),
      amount = amountOf(row)
    if (!kind || amount === null) continue
    const group = paymentGroup(row),
      total = totals.get(group) ?? {
        group,
        incoming: 0n,
        outgoing: 0n,
        internal: 0n,
        incomingCount: 0,
        outgoingCount: 0,
        internalCount: 0,
      }
    total[kind] += amount
    total[`${kind}Count`]++
    totals.set(group, total)
    if (kind === "internal") continue
    const other = party(row, kind === "incoming" ? "from" : "to")
    const byName =
      counterparties.get(group) ?? new Map<string, CounterpartyFlow>()
    const flow = byName.get(other.key) ?? {
      ...other,
      incoming: 0n,
      outgoing: 0n,
      count: 0,
    }
    flow[kind] += amount
    flow.count++
    byName.set(other.key, flow)
    counterparties.set(group, byName)
  }
  return { totals: [...totals.values()], counterparties }
}
export function activitySeries(rows: LedgerTransaction[]) {
  if (new Set(rows.map(paymentGroup)).size > 1)
    throw Error("Choose one currency and account type before charting amounts.")
  const months = new Map<
    string,
    { month: string; credit: bigint; debit: bigint; count: number }
  >()
  const categories = new Map<
    string,
    { category: string; credit: bigint; debit: bigint; count: number }
  >()
  let undated = 0
  for (const row of rows) {
    const amount = amountOf(row)
    if (amount === null) continue
    const kind = row.direction as "credit" | "debit",
      name = row.category || "Uncategorized"
    const category = categories.get(name) ?? {
      category: name,
      credit: 0n,
      debit: 0n,
      count: 0,
    }
    category[kind] += amount
    category.count++
    categories.set(name, category)
    const month = paymentDay(row)?.slice(0, 7)
    if (!month) {
      undated++
      continue
    }
    const period = months.get(month) ?? {
      month,
      credit: 0n,
      debit: 0n,
      count: 0,
    }
    period[kind] += amount
    period.count++
    months.set(month, period)
  }
  // Dense time axes are useful for normal statement ranges. For very long spans,
  // show only recorded months and explicitly disclose the omitted empty periods.
  const sorted = [...months.keys()].sort()
  let omittedEmptyMonths = false
  if (sorted.length) {
    const ordinal = (key: string) => {
      const [year, month] = key.split("-").map(Number)
      return year * 12 + month - 1
    }
    const start = ordinal(sorted[0]),
      end = ordinal(sorted.at(-1)!)
    omittedEmptyMonths = end - start > 600
    if (!omittedEmptyMonths)
      for (let cursor = start; cursor <= end; cursor++) {
        const key = `${String(Math.floor(cursor / 12)).padStart(4, "0")}-${String((cursor % 12) + 1).padStart(2, "0")}`
        if (!months.has(key))
          months.set(key, { month: key, credit: 0n, debit: 0n, count: 0 })
      }
  }
  return {
    omittedEmptyMonths,
    months: [...months.values()].sort((a, b) => a.month.localeCompare(b.month)),
    categories: [...categories.values()].sort(
      (a, b) => b.count - a.count || a.category.localeCompare(b.category)
    ),
    undated,
  }
}

export function analysisTableView(filters: AnalysisFilters) {
  return {
    ...(filters.fromNames.length ? { from_names: filters.fromNames } : {}),
    ...(filters.toNames.length ? { to_names: filters.toNames } : {}),
    ...(filters.perspectiveNames.length
      ? { perspective_names: filters.perspectiveNames }
      : {}),
    ...(filters.analysisGroup ? { analysis_group: filters.analysisGroup } : {}),
    ...(filters.analysisPeriod
      ? { analysis_period: filters.analysisPeriod }
      : {}),
    ...(filters.analysisDirection
      ? { analysis_direction: filters.analysisDirection }
      : {}),
    ...(filters.analysisCategories.length
      ? { analysis_categories: filters.analysisCategories }
      : {}),
    ...(filters.flowParty ? { flow_party: filters.flowParty } : {}),
    ...(filters.flowKind ? { flow_kind: filters.flowKind } : {}),
  }
}
export function sortAnalysisRows(rows: LedgerTransaction[], sort: string) {
  const [field, direction] = sort.split("-")
  if (!["description", "from", "to", "category"].includes(field)) return
  const value = (row: LedgerTransaction) =>
    field === "from" || field === "to"
      ? party(row, field).name
      : field === "category"
        ? row.category || "Uncategorized"
        : row.description || ""
  // Deterministic code-point ordering, mirrored by the export service.
  rows.sort((a, b) => {
    const left = value(a).toLowerCase(),
      right = value(b).toLowerCase()
    return (
      (left < right ? -1 : left > right ? 1 : 0) *
      (direction === "desc" ? -1 : 1)
    )
  })
}

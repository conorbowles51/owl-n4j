import { z } from "zod"
import { statementMonth } from "./statement-month"
export const historyPeriod = z.object({
  id: z.string(),
  source_document_id: z.string(),
  evidence_file_id: z.string().nullable(),
  filename: z.string().nullable(),
  start: z.string().nullable(),
  end: z.string().nullable(),
  opening_minor: z.string().nullable(),
  closing_minor: z.string().nullable(),
  status: z.enum(["reconciled", "confirmed_no_activity", "needs_review"]),
  transaction_count: z.number(),
  undated_count: z.number(),
  blockers: z.array(z.object({ message: z.string() }).passthrough()).optional(),
  assessment_current: z.boolean().optional(),
  activity: z.array(
    z.object({
      date: z.string(),
      count: z.number(),
      credit_minor: z.string(),
      debit_minor: z.string(),
    })
  ),
})
export const historyResponse = z.object({
  case_id: z.string(),
  applied: z.literal(false),
  groups: z.array(
    z.object({
      key: z.string(),
      account_id: z.string(),
      currency: z.string(),
      balance_kind: z.enum(["asset", "liability"]),
      label: z.string(),
      periods: z.array(historyPeriod),
    })
  ),
})
export type HistoryGroup = z.infer<typeof historyResponse>["groups"][number]
export type HistoryPeriod = z.infer<typeof historyPeriod>
export function accountColor(key: string) {
  let hash = 0
  for (const c of key) hash = (hash * 31 + c.charCodeAt(0)) >>> 0
  return `hsl(${hash % 360}, 65%, 42%)`
}
const ordinal = (day: string) => Date.parse(`${day}T00:00:00Z`) / 86400000

export function historyMonths(
  groups: HistoryGroup[],
  start?: string,
  end?: string
) {
  const dates = groups
    .flatMap((g) =>
      g.periods
        .flatMap((p) => [p.start, p.end, ...p.activity.map((a) => a.date)])
        .filter((d): d is string => !!d)
    )
    .sort()
  const first = start || dates[0],
    last = end || dates.at(-1)
  if (!first || !last) return []
  const result = []
  let month = first.slice(0, 7)
  while (month <= last.slice(0, 7)) {
    if (ordinal(month + "-01") - ordinal(first.slice(0, 7) + "-01") > 366 * 20)
      throw new Error(
        "Choose a date range of 20 years or less to compare monthly activity."
      )
    const bounds = statementMonth(month)!
    const lo = [bounds.period_start, first].sort().at(-1)!,
      hi = [bounds.period_end, last].sort()[0]
    const values = groups.map((group) => {
      const periods = group.periods.filter(
        (p) =>
          (p.start && p.end && p.start <= hi && p.end >= lo) ||
          p.activity.some((a) => a.date >= lo && a.date <= hi)
      )
      let cursor = ordinal(lo),
        overlap = false
      const windows = periods
        .filter((p) => p.start && p.end && p.status !== "needs_review")
        .map((p) => [
          Math.max(ordinal(p.start!), ordinal(lo)),
          Math.min(ordinal(p.end!), ordinal(hi)),
        ])
        .sort((a, b) => a[0] - b[0])
      for (const [a, b] of windows) {
        if (a < cursor) overlap = true
        if (a <= cursor) cursor = Math.max(cursor, b + 1)
      }
      const complete =
        cursor > ordinal(hi) &&
        !overlap &&
        !periods.some((p) => p.undated_count)
      // All competing periods count as overlap, including older unverified imports.
      const ordered = periods
        .filter((p) => p.start && p.end)
        .sort((a, b) => a.start!.localeCompare(b.start!))
      const ambiguous =
        overlap ||
        ordered.some(
          (p, i) => i > 0 && ordered.slice(0, i).some((q) => q.end! >= p.start!)
        )
      const readings = periods
        .flatMap((p) => p.activity)
        .filter((a) => a.date >= lo && a.date <= hi)
      const count = readings.reduce((sum, a) => sum + a.count, 0)
      const ends = periods
        .filter((p) => p.end && p.end >= lo && p.end <= hi)
        .sort((a, b) => b.end!.localeCompare(a.end!))
      const closing = !ambiguous && ends[0] ? ends[0].closing_minor : null
      return {
        key: group.key,
        periods,
        count: ambiguous || (!complete && !count) ? null : count,
        credit_minor:
          ambiguous || (!complete && !count)
            ? null
            : readings
                .reduce((sum, a) => sum + BigInt(a.credit_minor), 0n)
                .toString(),
        debit_minor:
          ambiguous || (!complete && !count)
            ? null
            : readings
                .reduce((sum, a) => sum + BigInt(a.debit_minor), 0n)
                .toString(),
        closing_minor: closing,
        closing_date: ends[0]?.end,
        state: ambiguous
          ? "Overlapping statements — compare sources"
          : complete
            ? count
              ? "Reconciled activity"
              : periods.some((p) => p.undated_count)
                ? "Payment dates need review"
                : "Confirmed no activity"
            : periods.length
              ? "Partial coverage or unverified reading"
              : "No statement available",
      }
    })
    // Selected filter bounds do not create evidence. Keep genuine quiet source
    // coverage, but omit months unsupported by every selected account.
    if (values.some((value) => value.periods.length || (value.count ?? 0) > 0))
      result.push({ month, start: lo, end: hi, values })
    const [y, m] = month.split("-").map(Number)
    month = `${m === 12 ? y + 1 : y}-${String(m === 12 ? 1 : m + 1).padStart(2, "0")}`
  }
  return result
}

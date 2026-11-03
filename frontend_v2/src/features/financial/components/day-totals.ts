import type { LedgerTransaction } from "../api"
import { formatLedgerAmount } from "../lib/ledger-format"

/**
 * Money in and out of one day's payments, per currency, from the amounts shown on the cards (exact integer minor
 * units). A currency with any amount that is not a whole number of minor units gets no total rather than a partial one.
 * Rows a correction replaced (superseded_by_id) are left out.
 */
export function dayTotals(rows: LedgerTransaction[]) {
  const by = new Map<string, { in: bigint; out: bigint; ok: boolean }>()
  for (const row of rows) {
    // A row a correction replaced is shown for its history but never summed: only the corrected value counts.
    if (row.superseded_by_id) continue
    const code = (row.currency || "").trim().toUpperCase()
    const entry = by.get(code) ?? { in: 0n, out: 0n, ok: true }
    const raw = String(row.amount_minor).replace(/^-/, "")
    if (!/^(0|[1-9][0-9]*)$/.test(raw)) entry.ok = false
    else if (row.direction === "credit") entry.in += BigInt(raw)
    else entry.out += BigInt(raw)
    by.set(code, entry)
  }
  return [...by.entries()]
    .filter(([, e]) => e.ok)
    .map(([currency, e]) => ({
      currency,
      in: formatLedgerAmount(e.in.toString(), currency).text,
      out: formatLedgerAmount(e.out.toString(), currency).text,
    }))
}

import { z } from "zod"
import { useState } from "react"
import { Button } from "@/components/ui/button"
import { LedgerSourceDialog } from "./LedgerSourceDialog"
import { RunningBalanceComparisonPanel } from "./RunningBalanceComparisonPanel"
import {
  correctionMoney,
  runningBalanceComparison,
} from "../lib/correction-contract"

const snapshot = z.object({
  running_balance_comparison: z.unknown().optional(),
  row: z.object({
    key: z.string(),
    ref_id: z.string(),
    amount_minor: z.string().regex(/^\d+$/),
    currency: z.string(),
    direction: z.enum(["credit", "debit"]),
  }),
})
export function CorrectionHistory({
  before,
  after,
  caseId,
}: {
  before: unknown
  after: unknown
  caseId?: string
}) {
  const [source, setSource] = useState<{
    caseId: string
    transactionId: string
  } | null>(null)
  const old = snapshot.safeParse(before)
  const replacement = snapshot.safeParse(after)
  if (!old.success || !replacement.success)
    return (
      <p className="text-xs">
        Correction reading history is unavailable or unrecognised.
      </p>
    )
  const recorded = replacement.data.running_balance_comparison
  const comparison = runningBalanceComparison.safeParse(recorded)
  const comparisonValid =
    comparison.success &&
    (!comparison.data.available ||
      (comparison.data.currency === old.data.row.currency &&
        comparison.data.currency === replacement.data.row.currency))
  return (
    <details className="text-xs">
      <summary>Original and replacement readings</summary>
      <p>
        Original {old.data.row.ref_id}:{" "}
        {correctionMoney(old.data.row.amount_minor, old.data.row.currency)}{" "}
        {old.data.row.direction}
      </p>
      <p>
        Replacement {replacement.data.row.ref_id}:{" "}
        {correctionMoney(
          replacement.data.row.amount_minor,
          replacement.data.row.currency
        )}{" "}
        {replacement.data.row.direction}
      </p>
      <p>
        These are the readings recorded at this decision, not a claim about
        their current status.
      </p>
      {recorded == null ? (
        <p>No running-balance comparison was recorded with this correction.</p>
      ) : comparisonValid ? (
        <div>
          <p>
            Saved comparison at the time of this correction; it has not been
            recalculated against later changes.
          </p>
          <RunningBalanceComparisonPanel
            key={`${caseId}:${replacement.data.row.key}`}
            caseId={caseId}
            comparison={comparison.data}
          />
        </div>
      ) : (
        <p>Saved running-balance comparison is unavailable or inconsistent.</p>
      )}
      {caseId && (
        <div className="flex flex-wrap gap-2 pt-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              setSource({ caseId, transactionId: old.data.row.key })
            }
          >
            View original source
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              setSource({ caseId, transactionId: replacement.data.row.key })
            }
          >
            View replacement source
          </Button>
        </div>
      )}
      {source && source.caseId === caseId && (
        <LedgerSourceDialog
          key={`${source.caseId}:${source.transactionId}`}
          caseId={source.caseId}
          transactionId={source.transactionId}
          onClose={() => setSource(null)}
        />
      )}
    </details>
  )
}

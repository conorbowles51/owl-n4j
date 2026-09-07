import { useState } from "react"
import { Button } from "@/components/ui/button"
import {
  correctionMoney,
  type RunningBalanceComparison,
} from "../lib/correction-contract"
import { LedgerSourceDialog } from "./LedgerSourceDialog"
export function RunningBalanceComparisonPanel({
  caseId,
  comparison,
}: {
  caseId?: string
  comparison: RunningBalanceComparison
}) {
  const [source, setSource] = useState<{
    caseId: string
    transactionId: string
  } | null>(null)
  return (
    <details className="space-y-2 rounded border p-3">
      <summary>Running-balance comparison</summary>
      {!comparison.available ? (
        <p>{comparison.reason}</p>
      ) : (
        <>
          <p>{comparison.limitation}</p>
          {comparison.interpretations.map((item) => (
            <div key={item.order} className="space-y-2">
              <p className="font-semibold">
                {item.order === "source_row_order"
                  ? "Assuming source row order"
                  : "Assuming reverse source row order"}
              </p>
              {(["current", "proposed"] as const).map((stage) => {
                const check = item[stage]
                return (
                  <div key={stage}>
                    <p>
                      {stage === "current"
                        ? "Current reading"
                        : "Proposed correction"}
                      : {check.compared_intervals} intervals compared;{" "}
                      {check.mismatch_count} mismatches.
                    </p>
                    <p>
                      {check.unanchored_balances} balances without an earlier
                      anchor; {check.excluded_rows} excluded rows interrupt the
                      chain; {check.trailing_rows_without_balance} trailing rows
                      have no ending balance check.
                    </p>
                    {check.findings.map((finding, index) => (
                      <p key={index}>
                        {finding.after_ref}: expected{" "}
                        {correctionMoney(
                          finding.expected_minor,
                          comparison.currency
                        )}
                        , printed{" "}
                        {correctionMoney(
                          finding.printed_minor,
                          comparison.currency
                        )}
                        , difference{" "}
                        {correctionMoney(
                          finding.delta_minor,
                          comparison.currency
                        )}
                        .
                        {caseId && (
                          <Button
                            variant="link"
                            onClick={() =>
                              setSource({
                                caseId,
                                transactionId: finding.after_transaction_id,
                              })
                            }
                          >
                            View source: {finding.after_ref}
                          </Button>
                        )}
                      </p>
                    ))}
                    {check.findings_truncated && (
                      <p>
                        Only the first 100 mismatches are displayed; the count
                        includes all comparisons.
                      </p>
                    )}
                  </div>
                )
              })}
            </div>
          ))}
        </>
      )}
      {source && source.caseId === caseId && (
        <LedgerSourceDialog
          caseId={source.caseId}
          transactionId={source.transactionId}
          onClose={() => setSource(null)}
        />
      )}
    </details>
  )
}

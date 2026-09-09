import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { assertCandidateScope, candidateUrl } from "../lib/candidate-contract"
import { currentRunningBalanceComparison } from "../lib/correction-contract"
import { RunningBalanceComparisonPanel } from "./RunningBalanceComparisonPanel"
const answer = z.object({
  case_id: z.string(),
  period_id: z.string(),
  source_document_id: z.string(),
  source_status: z.string(),
  proof_class: z.enum(["p0", "p1", "p2", "p3"]),
  applied: z.literal(false),
  checked_at: z.string(),
  comparison: currentRunningBalanceComparison,
})
export function StatementRunningBalances({
  caseId,
  periodId,
  sourceDocumentId,
  currency,
}: {
  caseId: string
  periodId: string
  sourceDocumentId: string
  currency: string
}) {
  const [opened, setOpened] = useState(false)
  const query = useQuery({
    queryKey: [
      "financial-ledger",
      caseId,
      "statement-running-balances",
      periodId,
      sourceDocumentId,
      currency,
    ],
    enabled: opened,
    retry: false,
    queryFn: async () => {
      const data = answer.parse(
        await fetchAPI<unknown>(
          candidateUrl(
            `statement-periods/${encodeURIComponent(periodId)}/running-balances`,
            caseId
          )
        )
      )
      assertCandidateScope(data, caseId)
      if (
        data.period_id !== periodId ||
        data.source_document_id !== sourceDocumentId ||
        (data.comparison.available && data.comparison.currency !== currency)
      )
        throw new Error(
          "The running-balance check does not match this statement."
        )
      return data
    },
  })
  return (
    <section
      className="space-y-2"
      aria-label="Current statement running balances"
    >
      <Button
        variant="outline"
        disabled={query.isFetching}
        onClick={() => (opened ? void query.refetch() : setOpened(true))}
      >
        {opened ? "Refresh running balances" : "Check running balances"}
      </Button>
      {opened &&
        (query.isPending ? (
          <p role="status">Checking stored running balances…</p>
        ) : query.isError ? (
          <p role="alert">
            Running balances unavailable. {query.error.message}
          </p>
        ) : (
          <>
            <p className="text-sm">
              Checked at {query.data.checked_at}. Source:{" "}
              {query.data.source_status} ·{" "}
              {query.data.proof_class.toUpperCase()}. No source eligibility or
              stored result was changed.
            </p>
            <RunningBalanceComparisonPanel
              key={`${caseId}:${periodId}:${query.data.checked_at}`}
              caseId={caseId}
              comparison={query.data.comparison}
              expanded
            />
          </>
        ))}
    </section>
  )
}

import { useState } from "react"
import type { LedgerQueryParams } from "../hooks/use-ledger-transactions"
import { LedgerFilters } from "./LedgerFilters"
import { LedgerSummaryPanel } from "./LedgerSummaryPanel"
import { LedgerTrendsPanel } from "./LedgerTrendsPanel"
import { RequestedCoveragePanel } from "./RequestedCoveragePanel"

export function LedgerAnalysis({ caseId }: { caseId: string | undefined }) {
  if (!caseId) return <p>Choose a case for ledger analysis.</p>
  return <CaseAnalysis key={caseId} caseId={caseId} />
}
function CaseAnalysis({ caseId }: { caseId: string }) {
  const [params, setParams] = useState<LedgerQueryParams>({})
  return (
    <section aria-label="Authoritative ledger trends" className="space-y-3 p-4">
      <h2 className="font-semibold">Ledger trends</h2>
      <p>
        Analysis of current ledger postings using recorded source eligibility
        and classification. Credits and debits stay separate by currency. Use
        the filters here to choose the account and ordering dates for this
        analysis.
      </p>
      <LedgerFilters caseId={caseId} onApply={setParams} />
      <RequestedCoveragePanel caseId={caseId} params={params} />
      <LedgerSummaryPanel caseId={caseId} params={params} />
      <LedgerTrendsPanel caseId={caseId} params={params} />
    </section>
  )
}

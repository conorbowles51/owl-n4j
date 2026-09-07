import { useState } from "react"
import type { LedgerQueryParams } from "../hooks/use-ledger-transactions"
import { LedgerExportButton } from "./LedgerExportButton"
import { LedgerFilters } from "./LedgerFilters"
import { LedgerSummaryPanel } from "./LedgerSummaryPanel"
import { LedgerCounterpartiesPanel } from "./LedgerCounterpartiesPanel"
import { RequestedCoveragePanel } from "./RequestedCoveragePanel"

export function LedgerCounterpartiesAnalysis({
  caseId,
}: {
  caseId: string | undefined
}) {
  if (!caseId) return <p>Choose a case for ledger analysis.</p>
  return <CaseAnalysis key={caseId} caseId={caseId} />
}
function CaseAnalysis({ caseId }: { caseId: string }) {
  const [params, setParams] = useState<LedgerQueryParams>({})
  return (
    <section
      aria-label="Authoritative ledger counterparties"
      className="space-y-3 p-4"
    >
      <h2 className="font-semibold">Ledger counterparty labels</h2>
      <p>
        Analysis of current ledger postings using recorded source eligibility
        and classification. Credits and debits stay separate by currency. Use
        the filters here to choose the account and ordering dates for this
        analysis.
      </p>
      <LedgerFilters caseId={caseId} onApply={setParams} />
      <RequestedCoveragePanel caseId={caseId} params={params} />
      <LedgerSummaryPanel caseId={caseId} params={params} />
      <LedgerExportButton caseId={caseId} params={params} />
      <LedgerCounterpartiesPanel caseId={caseId} params={params} />
    </section>
  )
}

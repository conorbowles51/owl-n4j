import {
  useInvestigationScope,
  useAnalysisPopulation,
} from "../stores/investigation-scope"
import { LedgerExportButton } from "./LedgerExportButton"
import { InvestigationFilters } from "./InvestigationFilters"
import { LedgerSummaryPanel } from "./LedgerSummaryPanel"
import { LedgerTrendsPanel } from "./LedgerTrendsPanel"
import { RequestedCoveragePanel } from "./RequestedCoveragePanel"

export function LedgerAnalysis({ caseId }: { caseId: string | undefined }) {
  if (!caseId) return <p>Choose a case for ledger analysis.</p>
  return <CaseAnalysis key={caseId} caseId={caseId} />
}
function CaseAnalysis({ caseId }: { caseId: string }) {
  const [population, setPopulation] = useAnalysisPopulation(caseId)
  const [params, setParams] = useInvestigationScope(caseId)
  return (
    <section aria-label="Authoritative ledger trends" className="space-y-3 p-4">
      <h2 className="font-semibold">Money over time</h2>
      <p>
        Choose an account or date range to explore its payments. Select a total
        to inspect the transactions and their original statements.
      </p>

      <InvestigationFilters
        key={JSON.stringify(params)}
        caseId={caseId}
        initialParams={params}
        onApply={setParams}
      />

      <LedgerSummaryPanel
        compact
        caseId={caseId}
        params={params}
        population={population}
      />

      <LedgerTrendsPanel
        autoLoad
        caseId={caseId}
        params={params}
        population={population}
      />
      <details className="rounded border p-3 space-y-3">
        <summary className="cursor-pointer font-medium">
          Analysis settings, statement coverage and downloads
        </summary>
        <label className="flex items-center gap-2">
          Payments to include
          <select
            aria-label="Payments to include"
            className="rounded border bg-background p-2"
            value={population}
            onChange={(e) =>
              setPopulation(e.target.value as "working" | "verified")
            }
          >
            <option value="working">All imported payments</option>
            <option value="verified">Verified payments only</option>
          </select>
        </label>
        <RequestedCoveragePanel caseId={caseId} params={params} />
        <LedgerExportButton caseId={caseId} params={params} />
      </details>
    </section>
  )
}

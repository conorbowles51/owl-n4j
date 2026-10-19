import { CounterpartyPartyDirectory } from "./CounterpartyPartyDirectory"
import { useState } from "react"
import {
  useInvestigationScope,
  useAnalysisPopulation,
} from "../stores/investigation-scope"
import { LedgerExportButton } from "./LedgerExportButton"
import { InvestigationFilters } from "./InvestigationFilters"
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
  const [population, setPopulation] = useAnalysisPopulation(caseId)
  const [identities, setIdentities] = useState(false)
  const [params, setParams] = useInvestigationScope(caseId)
  return (
    <section
      aria-label="Authoritative ledger counterparties"
      className="space-y-3 p-4"
    >
      <h2 className="font-semibold">People and businesses</h2>
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

      <label className="block">
        <input
          type="checkbox"
          aria-label="Group by reviewed payment identity"
          checked={identities}
          onChange={(e) => setIdentities(e.target.checked)}
        />{" "}
        Combine names I have linked to the same person or business
      </label>
      <LedgerCounterpartiesPanel
        autoLoad
        caseId={caseId}
        params={params}
        population={population}
        identities={identities}
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
      <details className="rounded border p-3">
        <summary className="cursor-pointer font-medium">
          Link different names for the same person or business
        </summary>
        <CounterpartyPartyDirectory key={caseId} caseId={caseId} />
      </details>
    </section>
  )
}

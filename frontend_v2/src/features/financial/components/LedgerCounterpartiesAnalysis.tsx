import { CounterpartyPartyDirectory } from "./CounterpartyPartyDirectory"
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
  const [population, setPopulation] = useState<"working" | "verified">(
    "working"
  )
  const [identities, setIdentities] = useState(false)
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
      <label className="flex items-center gap-2">
        Analysis population
        <select
          aria-label="Analysis population"
          className="rounded border bg-background p-2"
          value={population}
          onChange={(e) =>
            setPopulation(e.target.value as "working" | "verified")
          }
        >
          <option value="working">Working readings, including P3</option>
          <option value="verified">Verified totals only</option>
        </select>
      </label>
      <CounterpartyPartyDirectory key={caseId} caseId={caseId} />
      <LedgerFilters caseId={caseId} onApply={setParams} />
      <RequestedCoveragePanel caseId={caseId} params={params} />
      <LedgerSummaryPanel
        caseId={caseId}
        params={params}
        population={population}
      />
      <LedgerExportButton caseId={caseId} params={params} />
      <label className="block">
        <input
          type="checkbox"
          aria-label="Group by reviewed payment identity"
          checked={identities}
          onChange={(e) => setIdentities(e.target.checked)}
        />{" "}
        Group explicitly linked payments by reviewed identity
      </label>
      <LedgerCounterpartiesPanel
        caseId={caseId}
        params={params}
        population={population}
        identities={identities}
      />
    </section>
  )
}

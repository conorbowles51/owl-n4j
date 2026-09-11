import { SavePaymentSelection } from "./SavePaymentSelection"
import { useFinancialDraft } from "../stores/financial-drafts"
import {
  useInvestigationScope,
  useAnalysisPopulation,
} from "../stores/investigation-scope"
import { TransferReferenceEvidence } from "./TransferReferenceEvidence"
import { AccountFlowPerspective } from "./AccountFlowPerspective"
import { useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { candidateUrl } from "../lib/candidate-contract"
import { correctionMoney } from "../lib/correction-contract"
import { transferInputs, verifyTransferScenario } from "../lib/ledger-transfers"
import { LedgerSourceDialog } from "./LedgerSourceDialog"

export function LedgerTransfersWorkbench({
  caseId,
}: {
  caseId: string | undefined
}) {
  const [investigation, applyInvestigation] = useInvestigationScope(caseId)
  const start = investigation.startDate || ""
  const end = investigation.endDate || ""
  const [population, setPopulation] = useAnalysisPopulation(caseId)
  const [tolerance, setTolerance] = useFinancialDraft(
    caseId ?? "none",
    "transfer-days",
    3
  )
  if (!caseId) return <p>Choose a case to compare transfers.</p>
  return (
    <section aria-label="Ledger transfers" className="space-y-4 p-4">
      <h2 className="font-semibold">Transfers between accounts</h2>
      <p>
        Find money leaving one account and arriving in another. Open both
        statements, select the pairs you believe are transfers, and record why
        you linked them.
      </p>
      <p className="text-sm text-muted-foreground">
        The date range follows your other investigation tabs. Transfer
        comparison includes all accounts in that range so both sides can be
        found, even when another tab has a single account selected.
      </p>
      <div className="flex flex-wrap items-end gap-3">
        <label>
          From date
          <input
            aria-label="Transfer start date"
            className="block rounded border bg-background p-2"
            type="date"
            value={start}
            onChange={(e) =>
              applyInvestigation({
                ...investigation,
                startDate: e.target.value || undefined,
              })
            }
          />
        </label>
        <label>
          To date
          <input
            aria-label="Transfer end date"
            className="block rounded border bg-background p-2"
            type="date"
            value={end}
            onChange={(e) =>
              applyInvestigation({
                ...investigation,
                endDate: e.target.value || undefined,
              })
            }
          />
        </label>
        <label>
          Readings
          <select
            aria-label="Transfer population"
            className="block rounded border bg-background p-2"
            value={population}
            onChange={(e) =>
              setPopulation(e.target.value as "working" | "verified")
            }
          >
            <option value="working">All imported payments</option>
            <option value="verified">Verified payments only</option>
          </select>
        </label>
        <label>
          Maximum days between payments
          <select
            aria-label="Transfer date tolerance"
            className="block rounded border bg-background p-2"
            value={tolerance}
            onChange={(e) => setTolerance(Number(e.target.value))}
          >
            {Array.from({ length: 8 }, (_, i) => (
              <option key={i} value={i}>
                {i} days
              </option>
            ))}
          </select>
        </label>
      </div>
      <TransferScope
        key={JSON.stringify([caseId, start, end, population, tolerance])}
        caseId={caseId}
        start={start}
        end={end}
        population={population}
        tolerance={tolerance}
      />
    </section>
  )
}
function TransferScope({
  caseId,
  start,
  end,
  population,
  tolerance,
}: {
  caseId: string
  start: string
  end: string
  population: "working" | "verified"
  tolerance: number
}) {
  const [selected, setSelected] = useState<number[]>([]),
    [basis, setBasis] = useFinancialDraft(caseId, "transfer-basis", ""),
    [page, setPage] = useState(0),
    [source, setSource] = useState<string | null>(null)
  const load = useMutation({
    retry: false,
    mutationFn: async () => {
      const params = new URLSearchParams({
        population,
        tolerance_days: String(tolerance),
      })
      if (start) params.set("start_date", start)
      if (end) params.set("end_date", end)
      const data = transferInputs.parse(
        await fetchAPI<unknown>(
          `${candidateUrl("ledger-transfer-candidates", caseId)}&${params}`
        )
      )
      if (
        data.case_id !== caseId ||
        data.population !== population ||
        data.start_date !== (start || null) ||
        data.end_date !== (end || null) ||
        data.tolerance_days !== tolerance
      )
        throw Error("Transfer candidates returned for different filters.")
      return data
    },
    onSuccess: () => {
      setSelected([])
      setPage(0)
      setSource(null)
      scenario.reset()
    },
  })
  const scenario = useMutation({
    retry: false,
    mutationFn: async () => {
      if (!load.data || !selected.length || !basis.trim())
        throw Error("Select pairs and explain the basis.")
      const request = {
        expected_snapshot_sha256: load.data.snapshot_sha256,
        population,
        tolerance_days: tolerance,
        start_date: start || null,
        end_date: end || null,
        pairs: selected.map((i) => ({
          debit_id: load.data!.candidates[i].debit_id,
          credit_id: load.data!.candidates[i].credit_id,
        })),
        basis: basis.trim(),
      }
      return verifyTransferScenario(
        await fetchAPI<unknown>(
          candidateUrl("ledger-transfer-scenario", caseId),
          { method: "POST", body: request }
        ),
        load.data,
        request
      )
    },
  })
  const busy = load.isPending || scenario.isPending
  const used = new Set(
    selected.flatMap((i) =>
      load.data
        ? [load.data.candidates[i].debit_id, load.data.candidates[i].credit_id]
        : []
    )
  )
  const download = () => {
    if (!scenario.data) return
    const url = URL.createObjectURL(
      new Blob([scenario.data.scenario_json], { type: "application/json" })
    )
    const a = document.createElement("a")
    a.href = url
    a.download = "loupe-transfer-scenario.json"
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  return (
    <div className="space-y-3">
      <Button
        disabled={busy || Boolean(start && end && start > end)}
        onClick={() => {
          load.reset()
          scenario.reset()
          setSelected([])
          load.mutate()
        }}
      >
        Find possible transfers
      </Button>
      {load.isPending && <p role="status">Comparing payments…</p>}
      {load.isError && (
        <p role="alert">
          Transfer comparison unavailable. {load.error.message}
        </p>
      )}
      {load.data && !load.isPending && (
        <>
          <p>
            {load.data.rows.length} payments · {load.data.excluded_rows}{" "}
            excluded · {load.data.candidates.length} possible pairs
          </p>
          <details>
            <summary className="cursor-pointer">
              How possible transfers are matched
            </summary>
            <p>{load.data.limitation}</p>
          </details>
          <details>
            <summary className="cursor-pointer">
              Check repeated payment references (
              {load.data.reference_evidence.length})
            </summary>
            <TransferReferenceEvidence
              key={load.data.snapshot_sha256}
              data={load.data}
              onSource={setSource}
            />
          </details>
          {load.data.date_unavailable_ids.length > 0 && (
            <p>
              {load.data.date_unavailable_ids.length} payments have no
              transaction date and were not compared by date.
            </p>
          )}
          {load.data.candidates.length === 0 && (
            <p>
              No matching pair in this scope. Missing evidence, currencies or
              timing may prevent a match.
            </p>
          )}
          <ul className="space-y-3">
            {load.data.candidates
              .slice(page * 25, page * 25 + 25)
              .map((pair, offset) => {
                const index = page * 25 + offset,
                  debit = load.data!.rows.find((r) => r.key === pair.debit_id)!,
                  credit = load.data!.rows.find(
                    (r) => r.key === pair.credit_id
                  )!,
                  checked = selected.includes(index)
                return (
                  <li
                    key={`${pair.debit_id}:${pair.credit_id}`}
                    className="space-y-2 rounded border p-3"
                  >
                    <label className="flex items-center gap-2">
                      <input
                        aria-label={`Pair transfer ${index + 1}`}
                        type="checkbox"
                        checked={checked}
                        disabled={
                          busy ||
                          (!checked &&
                            (used.has(pair.debit_id) ||
                              used.has(pair.credit_id)))
                        }
                        onChange={() => {
                          setSelected((v) =>
                            checked
                              ? v.filter((i) => i !== index)
                              : [...v, index]
                          )
                          scenario.reset()
                        }}
                      />
                      <strong>
                        {correctionMoney(pair.amount_minor, pair.currency)}
                      </strong>
                      <span>
                        {pair.outcome === "ambiguous"
                          ? "More than one possible match. Compare the alternatives."
                          : pair.match_basis === "exact_reference"
                            ? "Matching payment reference"
                            : "Matching amount and nearby date"}
                      </span>
                    </label>
                    <div className="grid items-center gap-3 md:grid-cols-[1fr_auto_1fr]">
                      <div>
                        <p>
                          Money out ·{" "}
                          {debit.account_label ||
                            `account ${debit.account_id.slice(0, 8)}`}
                        </p>
                        <p>
                          {debit.ordering_date} ·{" "}
                          {debit.description ?? "No description"}
                        </p>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => setSource(debit.key)}
                        >
                          Open debit source {index + 1}
                        </Button>
                      </div>
                      <span aria-hidden="true" className="text-2xl">
                        →
                      </span>
                      <div>
                        <p>
                          Money in ·{" "}
                          {credit.account_label ||
                            `account ${credit.account_id.slice(0, 8)}`}
                        </p>
                        <p>
                          {credit.ordering_date} ·{" "}
                          {credit.description ?? "No description"}
                        </p>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => setSource(credit.key)}
                        >
                          Open credit source {index + 1}
                        </Button>
                      </div>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {pair.reference
                        ? `Shared ${pair.reference.kind}: ${pair.reference.value}. `
                        : ""}
                      {pair.compared_date_field
                        ? `${pair.date_gap_days} days apart using the recorded payment dates. `
                        : "Matched by reference; the dates may be farther apart than your chosen limit. "}
                      Matching values alone do not establish a transfer.
                    </p>
                  </li>
                )
              })}
          </ul>
          {load.data.candidates.length > 25 && (
            <div className="flex gap-2">
              <Button
                disabled={!page || busy}
                onClick={() => setPage((v) => v - 1)}
              >
                Previous transfer pairs
              </Button>
              <Button
                disabled={
                  (page + 1) * 25 >= load.data!.candidates.length || busy
                }
                onClick={() => setPage((v) => v + 1)}
              >
                Next transfer pairs
              </Button>
            </div>
          )}
          {load.data.candidates.length > 0 && (
            <fieldset disabled={busy} className="space-y-2 rounded border p-3">
              <legend>Explain your selected transfers</legend>
              <p>
                {selected.length} pairs selected. Each payment can belong to
                only one selected pair.
              </p>
              <label className="block">
                Why do you think these payments are transfers?
                <textarea
                  aria-label="Basis for transfer pairings"
                  className="block w-full rounded border bg-background p-2"
                  value={basis}
                  maxLength={4096}
                  onChange={(e) => {
                    setBasis(e.target.value)
                    scenario.reset()
                  }}
                />
              </label>
              <Button
                disabled={!selected.length || !basis.trim()}
                onClick={() => scenario.mutate()}
              >
                Compare totals using these transfers
              </Button>
            </fieldset>
          )}
        </>
      )}
      {scenario.isPending && (
        <p role="status">Checking the current ledger and selected pairs…</p>
      )}
      {scenario.isError && (
        <p role="alert">Scenario unavailable. {scenario.error.message}</p>
      )}
      {scenario.data && (
        <section
          aria-label="Paired transfer scenario"
          className="space-y-2 rounded border p-3"
        >
          <h3 className="font-semibold">
            Totals using your selected transfers
          </h3>
          <p>
            Selected pairs count once here. These assumptions do not change
            ledger totals or verify a transfer.
          </p>
          {scenario.data.figures.map((f) => (
            <div key={f.currency}>
              <p>
                {f.currency}: {f.posting_rows} payments represented as{" "}
                {f.movement_count} movements, including {f.paired_transfers}{" "}
                selected transfers.
              </p>
              <p>
                Paired amount:{" "}
                {correctionMoney(f.paired_amount_minor, f.currency)} · Unpaired
                credits: {correctionMoney(f.unpaired_credits_minor, f.currency)}{" "}
                · Unpaired debits:{" "}
                {correctionMoney(f.unpaired_debits_minor, f.currency)}
              </p>
            </div>
          ))}
          {load.data && (
            <SavePaymentSelection
              caseId={caseId}
              ids={[...used]}
              analysis={{
                kind: "transfer-comparison",
                summary: `Saves ${selected.length} selected transfer pairs, your explanation and the calculated totals.`,
                details: {
                  snapshot_sha256: load.data.snapshot_sha256,
                  scenario_sha256: scenario.data.scenario_sha256,
                  pairs: selected.map((i) => load.data!.candidates[i]),
                  basis,
                  figures: scenario.data.figures,
                  start_date: start || null,
                  end_date: end || null,
                  tolerance_days: tolerance,
                  population,
                },
              }}
            />
          )}
          <Button onClick={download}>
            Download scenario with source references
          </Button>
        </section>
      )}
      {load.data && !load.isPending && (
        <AccountFlowPerspective
          key={load.data.snapshot_sha256}
          scope={load.data}
          scenarioJson={scenario.data?.scenario_json}
          onSource={setSource}
        />
      )}
      {source && (
        <LedgerSourceDialog
          caseId={caseId}
          transactionId={source}
          onClose={() => setSource(null)}
        />
      )}
    </div>
  )
}

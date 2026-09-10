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
  const [start, setStart] = useState(""),
    [end, setEnd] = useState("")
  const [population, setPopulation] = useState<"working" | "verified">(
    "working"
  )
  const [tolerance, setTolerance] = useState(3)
  if (!caseId) return <p>Choose a case to compare transfers.</p>
  return (
    <section aria-label="Ledger transfers" className="space-y-4 p-4">
      <h2 className="font-semibold">Transfers between accounts</h2>
      <p>
        Compare current debit and credit readings across the accounts in this
        case. Inspect both sources before selecting a pairing. The ledger
        retains both original postings.
      </p>
      <div className="flex flex-wrap items-end gap-3">
        <label>
          From ordering date
          <input
            aria-label="Transfer start date"
            className="block rounded border bg-background p-2"
            type="date"
            value={start}
            onChange={(e) => setStart(e.target.value)}
          />
        </label>
        <label>
          To ordering date
          <input
            aria-label="Transfer end date"
            className="block rounded border bg-background p-2"
            type="date"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
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
            <option value="working">Working, including P3</option>
            <option value="verified">Verified only</option>
          </select>
        </label>
        <label>
          Date tolerance
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
    [basis, setBasis] = useState(""),
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
      {load.isPending && <p role="status">Comparing current readings…</p>}
      {load.isError && (
        <p role="alert">
          Transfer comparison unavailable. {load.error.message}
        </p>
      )}
      {load.data && !load.isPending && (
        <>
          <p>
            {load.data.rows.length} current readings · {load.data.excluded_rows}{" "}
            excluded · {load.data.candidates.length} possible pairs
          </p>
          <p className="text-muted-foreground">{load.data.limitation}</p>
          {load.data.date_unavailable_ids.length > 0 && (
            <p>
              {load.data.date_unavailable_ids.length} readings use statement-end
              ordering only and were not compared as dated transfers.
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
                          ? "Multiple possible partners — inspect alternatives"
                          : "Unique amount/date candidate"}
                      </span>
                    </label>
                    <div className="grid items-center gap-3 md:grid-cols-[1fr_auto_1fr]">
                      <div>
                        <p>
                          Money out · account {debit.account_id.slice(0, 8)}
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
                          Money in · account {credit.account_id.slice(0, 8)}
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
                      {pair.date_gap_days} days apart using{" "}
                      {pair.compared_date_field}. Matching values alone do not
                      establish a transfer.
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
              <legend>Separate pairing scenario</legend>
              <p>
                {selected.length} pairs selected. Each reading can belong to
                only one selected pair.
              </p>
              <label className="block">
                Basis for these pairings
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
                Calculate paired movement scenario
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
          <h3 className="font-semibold">Conditional movement totals</h3>
          <p>
            Selected pairs count once here. These assumptions do not change
            ledger totals or verify a transfer.
          </p>
          {scenario.data.figures.map((f) => (
            <div key={f.currency}>
              <p>
                {f.currency}: {f.posting_rows} postings represented as{" "}
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

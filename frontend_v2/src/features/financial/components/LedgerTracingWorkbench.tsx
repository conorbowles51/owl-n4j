import { IndirectReviewWorkbench } from "./IndirectReviewWorkbench"
import { TraceAssetFields, TraceAssetResultsPanel } from "./TraceAssetFields"
import type { TraceAssetUse } from "../lib/trace-assets"
import { useState } from "react"
import { fetchAPI } from "@/lib/api-client"
import { Button } from "@/components/ui/button"
import { candidateUrl } from "../lib/candidate-contract"
import {
  methods,
  traceInputs,
  verifyTraceResponse,
  type TraceInputs,
} from "../lib/ledger-trace"
import type { LedgerQueryParams } from "../hooks/use-ledger-transactions"
import { LedgerFilters } from "./LedgerFilters"
import { NetworkTracingWorkbench } from "./NetworkTracingWorkbench"
import { TraceAttributionFields } from "./TraceAttributionFields"
import { LedgerSourceDialog } from "./LedgerSourceDialog"
import { correctionMinor, correctionMoney } from "../lib/correction-contract"
import { RequestedCoveragePanel } from "./RequestedCoveragePanel"

export function LedgerTracingWorkbench({
  caseId,
}: {
  caseId: string | undefined
}) {
  const [mode, setMode] = useState("single")
  if (!caseId) return <p>Choose a case for tracing.</p>
  return (
    <div>
      <div className="flex gap-2 p-4">
        <Button
          variant={mode === "single" ? "primary" : "outline"}
          onClick={() => setMode("single")}
        >
          Trace one account
        </Button>
        <Button
          variant={mode === "network" ? "primary" : "outline"}
          onClick={() => setMode("network")}
        >
          Trace between accounts
        </Button>
        <Button
          variant={mode === "indirect" ? "primary" : "outline"}
          onClick={() => setMode("indirect")}
        >
          Indirect review methods
        </Button>
      </div>
      {mode === "indirect" ? (
        <IndirectReviewWorkbench key={caseId} caseId={caseId} />
      ) : mode === "single" ? (
        <CaseTracing key={caseId} caseId={caseId} />
      ) : (
        <NetworkTracingWorkbench key={caseId} caseId={caseId} />
      )}
    </div>
  )
}
function CaseTracing({ caseId }: { caseId: string }) {
  const [params, setParams] = useState<LedgerQueryParams>({})
  const [population, setPopulation] = useState<"working" | "verified">(
    "verified"
  )
  return (
    <section aria-label="Conditional ledger tracing" className="space-y-4 p-4">
      <h2 className="font-semibold">Conditional account tracing</h2>
      <p>
        Explore how selected calculation rules allocate withdrawals. Opening
        funds, deposit attribution and same-day order are your assumptions.
        Results do not establish ownership or which legal rule applies.
      </p>
      <LedgerFilters caseId={caseId} onApply={setParams} />
      <RequestedCoveragePanel caseId={caseId} params={params} />
      <label>
        Tracing population{" "}
        <select
          aria-label="Tracing population"
          className="border bg-background p-2"
          value={population}
          onChange={(e) =>
            setPopulation(e.target.value as "working" | "verified")
          }
        >
          <option value="verified">Verified only</option>
          <option value="working">Working readings, including P3</option>
        </select>
      </label>
      <ScopedTracing
        key={JSON.stringify([params, population])}
        population={population}
        caseId={caseId}
        params={params}
      />
    </section>
  )
}
function ScopedTracing({
  population,
  caseId,
  params,
}: {
  caseId: string
  params: LedgerQueryParams
  population: "working" | "verified"
}) {
  const [inputs, setInputs] = useState<TraceInputs | null>(null)
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("")
  const load = async () => {
    setBusy(true)
    setError("")
    setInputs(null)
    try {
      const search = new URLSearchParams({
        population,
        account_id: params.accountId!,
        start_date: params.startDate!,
        end_date: params.endDate!,
      })
      const value = traceInputs.parse(
        await fetchAPI(
          `${candidateUrl("ledger-trace-inputs", caseId)}&${search}`,
          { timeout: 120000 }
        )
      )
      if (
        value.population !== population ||
        value.case_id !== caseId ||
        value.account_id !== params.accountId ||
        value.start_date !== params.startDate ||
        value.end_date !== params.endDate
      )
        throw new Error("Tracing inputs belong to different filters.")
      setInputs(value)
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Could not load tracing inputs."
      )
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="space-y-3">
      <p>
        Choose one account and both ordering-date bounds, then load its eligible
        readings. Missing evidence can change every result.
      </p>
      <Button
        disabled={
          busy || !params.accountId || !params.startDate || !params.endDate
        }
        onClick={() => void load()}
      >
        {busy ? "Loading…" : "Load tracing inputs"}
      </Button>
      {error && <p role="alert">{error}</p>}
      {inputs && <ScenarioForm key={inputs.snapshot_sha256} inputs={inputs} />}
    </div>
  )
}
function ScenarioForm({ inputs }: { inputs: TraceInputs }) {
  const [rows, setRows] = useState(() =>
    [...inputs.readings].sort((a, b) =>
      a.row.ordering_date.localeCompare(b.row.ordering_date)
    )
  )
  const [source, setSource] = useState<string | null>(null)
  const [opening, setOpening] = useState(""),
    [openingBasis, setOpeningBasis] = useState("")
  const [orderBasis, setOrderBasis] = useState("")
  const [assetUses, setAssetUses] = useState<TraceAssetUse[]>([])
  const [attributions, setAttributions] = useState([
    { transaction_id: "", claim_id: "", amount_input: "", basis: "" },
  ])
  const [selected, setSelected] = useState<string[]>([]),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("")
  const [result, setResult] = useState<Awaited<
    ReturnType<typeof verifyTraceResponse>
  > | null>(null)
  const calculate = async () => {
    setBusy(true)
    setError("")
    setResult(null)
    const request = {
      population: inputs.population,
      account_id: inputs.account_id,
      start_date: inputs.start_date,
      end_date: inputs.end_date,
      expected_snapshot_sha256: inputs.snapshot_sha256,
      opening_balance_minor: correctionMinor(opening, inputs.currency),
      opening_basis: openingBasis,
      order_basis: orderBasis,
      ordered_transaction_ids: rows.map((r) => r.row.key),
      attributions: attributions.map(({ amount_input, ...a }) => ({
        ...a,
        amount_minor: correctionMinor(amount_input, inputs.currency),
      })),
      asset_uses: assetUses.map(({ asset_amount_input, ...use }) => ({
        ...use,
        ...(asset_amount_input === undefined
          ? {}
          : {
              asset_amount_minor: correctionMinor(
                asset_amount_input,
                inputs.currency
              ),
              allocation_basis: "proportional_share",
            }),
      })),
      doctrines: selected,
    }
    try {
      if (
        request.opening_balance_minor === null ||
        request.attributions.some(
          (a) => a.amount_minor === null || a.amount_minor === "0"
        )
      )
        throw Error(
          `Enter valid ${inputs.currency} amounts without separators; attributed amounts must be greater than zero.`
        )
      setResult(
        await verifyTraceResponse(
          await fetchAPI(candidateUrl("ledger-trace", inputs.case_id), {
            method: "POST",
            body: request,
            timeout: 120000,
          }),
          inputs,
          request
        )
      )
    } catch (e) {
      setError(e instanceof Error ? e.message : "Tracing failed.")
    } finally {
      setBusy(false)
    }
  }
  const download = () => {
    if (!result) return
    const url = URL.createObjectURL(
      new Blob([result.envelope.scenario_json], { type: "application/json" })
    )
    const link = document.createElement("a")
    link.href = url
    link.download = "loupe-conditional-trace.json"
    link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  return (
    <div className="space-y-4">
      <p>
        {inputs.included_rows} {inputs.population} scenario readings;{" "}
        {inputs.excluded_rows} excluded readings. Currency: {inputs.currency}.
        Enter amounts in currency units, using a decimal point where needed and
        no thousands separators.
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          void calculate()
        }}
        onChange={() => {
          setResult(null)
          setError("")
        }}
      >
        <fieldset disabled={busy} className="space-y-3">
          <legend className="font-semibold">
            Record your scenario assumptions
          </legend>
          <label className="block">
            Opening balance ({inputs.currency}){" "}
            <input
              className="border p-1"
              required
              inputMode="decimal"
              maxLength={32}
              value={opening}
              onChange={(e) => setOpening(e.target.value)}
            />
          </label>
          <label className="block">
            Opening balance basis{" "}
            <textarea
              className="block w-full border p-1"
              required
              value={openingBasis}
              onChange={(e) => setOpeningBasis(e.target.value)}
            />
          </label>
          <p>
            Review every movement below. Use Move earlier only to change the
            order within the same date. The displayed order is not a verified
            bank sequence.
          </p>
          <ol className="max-h-80 overflow-auto border p-3">
            {rows.map((r, i) => (
              <li className="border-b py-2" key={r.row.key}>
                {i + 1}. {r.row.ordering_date} — {r.row.direction}{" "}
                {correctionMoney(r.row.amount_minor, inputs.currency)} —{" "}
                {r.row.description}
                <br />
                <small>Ledger reading: {r.row.key}</small>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setSource(r.row.key)}
                >
                  Open tracing source {i + 1}
                </Button>
                {i > 0 &&
                  rows[i - 1].row.ordering_date === r.row.ordering_date && (
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => {
                        setResult(null)
                        setRows((old) => {
                          const next = [...old]
                          ;[next[i - 1], next[i]] = [next[i], next[i - 1]]
                          return next
                        })
                      }}
                    >
                      Move earlier: reading {i + 1}
                    </Button>
                  )}
              </li>
            ))}
          </ol>
          <label className="block">
            Basis for accepting this movement order{" "}
            <textarea
              className="block w-full border p-1"
              required
              value={orderBasis}
              onChange={(e) => setOrderBasis(e.target.value)}
            />
          </label>
          <TraceAssetFields
            value={assetUses}
            onChange={(v) => {
              setAssetUses(v)
              setResult(null)
              setError("")
            }}
            withdrawals={rows
              .filter(
                (r) =>
                  r.row.direction === "debit" && BigInt(r.row.amount_minor) > 0n
              )
              .map(({ row: r }) => ({
                id: r.key,
                label: `${r.ordering_date} · ${correctionMoney(r.amount_minor, inputs.currency)}`,
              }))}
          />
          <TraceAttributionFields
            currency={inputs.currency}
            credits={rows
              .filter((r) => r.row.direction === "credit")
              .map((r) => ({
                id: r.row.key,
                label: `${r.row.ordering_date} — ${correctionMoney(r.row.amount_minor, inputs.currency)} — ${r.row.key}`,
              }))}
            value={attributions}
            onChange={(next) => {
              setAttributions(next)
              setResult(null)
              setError("")
            }}
          />
          <p>
            Choose calculation methods explicitly. No method is recommended by
            this screen.
          </p>
          {methods.map((method) => (
            <label className="block" key={method}>
              <input
                type="checkbox"
                checked={selected.includes(method)}
                onChange={(e) =>
                  setSelected((old) =>
                    e.target.checked
                      ? [...old, method]
                      : old.filter((m) => m !== method)
                  )
                }
              />{" "}
              {method.replaceAll("_", " ")}
            </label>
          ))}
          <Button type="submit" disabled={!selected.length || busy}>
            {busy ? "Calculating…" : "Calculate conditional scenario"}
          </Button>
        </fieldset>
      </form>
      {error && <p role="alert">{error}</p>}
      {source && (
        <LedgerSourceDialog
          caseId={inputs.case_id}
          transactionId={source}
          onClose={() => setSource(null)}
        />
      )}
      {result && (
        <section aria-label="Conditional tracing results" className="space-y-3">
          <h3 className="font-semibold">
            Conditional results — assumptions unverified
          </h3>
          {result.value.limitations.map((note) => (
            <p key={note}>{note}</p>
          ))}
          {Object.entries(result.value.comparison.results).map(
            ([method, output]) => (
              <div className="border p-3" key={method}>
                <h4>{method.replaceAll("_", " ")}</h4>
                <TraceAssetResultsPanel
                  items={result.value.asset_uses[method] ?? []}
                  onSource={setSource}
                />
                {Object.entries(output.outcomes).map(([id, outcome]) => (
                  <p key={id}>
                    {id}: attributed{" "}
                    {correctionMoney(
                      outcome.deposited.minor_units,
                      inputs.currency
                    )}
                    ; surviving{" "}
                    {correctionMoney(
                      outcome.surviving.minor_units,
                      inputs.currency
                    )}
                    ; withdrawn{" "}
                    {correctionMoney(
                      outcome.withdrawn.minor_units,
                      inputs.currency
                    )}
                    .
                  </p>
                ))}
                <p>
                  Withdrawals left unidentified:{" "}
                  {output.draws
                    .reduce(
                      (n, d) => n + BigInt(d.unidentified.minor_units),
                      0n
                    )
                    .toString()}
                  . Withdrawals without available funds:{" "}
                  {output.draws
                    .reduce((n, d) => n + BigInt(d.unfunded.minor_units), 0n)
                    .toString()}{" "}
                  ({inputs.currency} minor units).
                </p>
                <p>
                  Unidentified withdrawals mean the method did not establish
                  whose funds left; surviving amounts must be read alongside
                  this uncertainty.
                </p>
                {output.notes.map((note, i) => (
                  <p key={i}>{note}</p>
                ))}
              </div>
            )
          )}
          <Button onClick={download}>Download conditional scenario</Button>
          <p>
            Includes captured ledger readings and history, explicit assumptions
            and calculation details. SHA-256: {result.envelope.scenario_sha256}
          </p>
        </section>
      )}
    </div>
  )
}

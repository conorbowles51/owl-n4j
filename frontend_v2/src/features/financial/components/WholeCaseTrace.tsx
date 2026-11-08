import { useState } from "react"
import { Button } from "@/components/ui/button"
import { correctionMinor, correctionMoney } from "../lib/correction-contract"
import { traceMethods } from "../lib/trace-methods"
import { useWholeCasePage, useWholeCaseRun, wholeCaseFileUrl } from "../lib/whole-case-run"
import { WholeCasePager, WholeCaseProgress } from "./WholeCaseProgress"
import { WholeCaseSources } from "./WholeCaseSources"

const PAGE = 25
const n = (value: number) => value.toLocaleString("en-US")

interface Row {
  key: string
  account_id: string
  account_label: string | null
  ordering_date: string
  amount_minor: string
  currency: string
  direction: string
  description: string | null
}
interface Pair {
  debit_id: string
  credit_id: string
  amount_minor: string
  currency: string
  debit: { account_id: string; account_label: string | null; ordering_date: string }
  credit: { account_id: string; account_label: string | null; ordering_date: string }
}
interface Comparison {
  snapshot_sha256: string
  currencies: { currency: string; rows: number }[]
  accounts?: { account_id: string; label: string | null; rows: number }[]
}
interface AssetUse {
  transaction_id: string
  asset_label: string
  basis: string
  amount_minor: string
  asset_amount_minor: string
  currency: string
  allocated_by_claim: Record<string, string>
  outside_claims_minor: string
  limitation: string
}
interface TraceSummary {
  readings: number
  accounts: { account_id: string; label: string | null; steps_from_start: number }[]
  stopped: boolean
  stop_words: string | null
  continue_with_steps: number | null
  same_day_moves: number
  scenario_sha256: string
  backward_timing_used?: boolean
  methods: Record<
    string,
    {
      hops: number
      unidentified_withdrawals_minor: string
      asset_uses?: AssetUse[]
      claims: Record<string, { root_attributed_minor: string; reported_remaining_minor: string; withdrawn_without_selected_transfer_minor: string }>
    }
  >
}

/**
 * A trace above one screen's size. It starts at chosen payments and follows chosen transfers a stated number of steps,
 * so its size follows the trace, not the case: only the accounts it reaches are read. A trace that reaches its step
 * limit says exactly where it stopped and continues with one more step.
 */
export function WholeCaseTrace({
  caseId,
  start,
  end,
  population,
  tolerance = 3,
}: {
  caseId: string
  start: string | null
  end: string | null
  population: string
  tolerance?: number
}) {
  const dates = { ...(start ? { start_date: start } : {}), ...(end ? { end_date: end } : {}) }
  const comparison = useWholeCaseRun<Comparison>(caseId, { kind: "transfers", population, tolerance_days: tolerance, ...dates })
  const [currency, setCurrency] = useState("")
  const [search, setSearch] = useState("")
  const [offset, setOffset] = useState(0)
  const [pairSearch, setPairSearch] = useState("")
  const [pairOffset, setPairOffset] = useState(0)
  const [claim, setClaim] = useState<{ row: Row; id: string; amount: string; basis: string } | null>(null)
  const [pairs, setPairs] = useState<Pair[]>([])
  const [openings, setOpenings] = useState<Record<string, string>>({})
  const [openingBasis, setOpeningBasis] = useState("")
  const [pairBasis, setPairBasis] = useState("")
  const [orderBasis, setOrderBasis] = useState("")
  const [steps, setSteps] = useState(3)
  const [methods, setMethods] = useState<string[]>([])
  const [assetSearch, setAssetSearch] = useState("")
  const [assetOffset, setAssetOffset] = useState(0)
  const [assetUses, setAssetUses] = useState<{ row: Row; label: string; basis: string }[]>([])
  const [allowBackward, setAllowBackward] = useState(false)
  const [backwardBasis, setBackwardBasis] = useState("")
  const [request, setRequest] = useState<Record<string, unknown> | null>(null)
  const run = comparison.run
  const rows = useWholeCasePage<Row>(caseId, search.trim() ? run : undefined, "rows@credit", offset, PAGE, search)
  const debits = useWholeCasePage<Row>(caseId, assetSearch.trim() ? run : undefined, "rows@debit", assetOffset, PAGE, assetSearch)
  const candidates = useWholeCasePage<Pair>(caseId, run, "candidates", pairOffset, PAGE, pairSearch)
  const trace = useWholeCaseRun<TraceSummary>(caseId, request ?? {}, "whole-case-runs/trace", request !== null)
  if (!run || run.status !== "completed" || !run.summary)
    return <WholeCaseProgress run={run} error={comparison.error} noun="comparison" onAgain={comparison.again} />
  const summary = run.summary
  const chosenCurrency = currency || summary.currencies[0]?.currency || ""
  const accounts = new Map<string, string>()
  if (claim) accounts.set(claim.row.account_id, claim.row.account_label ?? claim.row.account_id)
  for (const pair of pairs) {
    accounts.set(pair.debit.account_id, pair.debit.account_label ?? pair.debit.account_id)
    accounts.set(pair.credit.account_id, pair.credit.account_label ?? pair.credit.account_id)
  }
  const amount = claim ? correctionMinor(claim.amount, chosenCurrency) : null
  const ready =
    claim &&
    claim.id.trim() &&
    claim.basis.trim() &&
    amount &&
    methods.length &&
    orderBasis.trim() &&
    openingBasis.trim() &&
    (!pairs.length || pairBasis.trim()) &&
    (!allowBackward || backwardBasis.trim()) &&
    assetUses.every((use) => use.label.trim() && use.basis.trim()) &&
    [...accounts.keys()].every((id) => correctionMinor(openings[id] ?? "", chosenCurrency) !== null)
  const submit = (limit: number) => {
    setSteps(limit)
    setRequest({
      expected_snapshot_sha256: summary.snapshot_sha256,
      population,
      tolerance_days: tolerance,
      start_date: start || null,
      end_date: end || null,
      currency: chosenCurrency,
      steps: limit,
      attributions: [
        { transaction_id: claim!.row.key, claim_id: claim!.id.trim(), amount_minor: amount, basis: claim!.basis.trim() },
      ],
      pairs: pairs.map((p) => ({ debit_id: p.debit_id, credit_id: p.credit_id })),
      openings: [...accounts.keys()].map((id) => ({
        account_id: id,
        amount_minor: correctionMinor(openings[id] ?? "", chosenCurrency),
        basis: openingBasis.trim(),
      })),
      basis: pairBasis.trim(),
      order_basis: orderBasis.trim(),
      doctrines: methods,
      asset_uses: assetUses.map((use) => ({
        transaction_id: use.row.key,
        asset_label: use.label.trim(),
        basis: use.basis.trim(),
      })),
      allow_backward: allowBackward,
      backward_basis: allowBackward ? backwardBasis.trim() : "",
    })
  }
  const result = trace.run?.status === "completed" ? trace.run.summary : undefined
  return (
    <div className="space-y-4">
      <p>
        This scope holds {n(run.counts?.rows ?? 0)} payments. A trace starts at a payment you choose and follows the
        transfers you select, so only the accounts it reaches are read and every one of their payments is included.
      </p>
      <label className="block">
        Currency{" "}
        <select className="border bg-background p-2" aria-label="Trace currency" value={chosenCurrency} onChange={(e) => setCurrency(e.target.value)}>
          {summary.currencies.map((c) => (
            <option key={c.currency} value={c.currency}>
              {c.currency} ({n(c.rows)} payments)
            </option>
          ))}
        </select>
      </label>
      <fieldset className="space-y-2 rounded border p-3">
        <legend>1. Choose the payment the trace starts from</legend>
        <input
          aria-label="Search money-in payments"
          placeholder="Name, date, description or amount"
          className="block w-full border bg-background p-2"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value)
            setOffset(0)
          }}
        />
        {search.trim() && <p className="text-sm">{n(rows.data?.total ?? 0)} money-in payments match.</p>}
        <ul className="space-y-1 text-sm">
          {rows.data?.items
            .filter((row) => row.currency === chosenCurrency)
            .map((row) => (
              <li key={row.key} className="flex items-center gap-2">
                <Button size="sm" variant="outline" onClick={() => setClaim({ row, id: "claim", amount: "", basis: "" })}>
                  Start here
                </Button>
                {row.ordering_date} · {row.account_label} · {correctionMoney(row.amount_minor, row.currency)} · {row.description}
              </li>
            ))}
        </ul>
        <WholeCasePager label="payments" offset={offset} size={PAGE} total={rows.data?.total ?? 0} onOffset={setOffset} />
        {claim && (
          <div className="space-y-1 text-sm">
            <p>
              Start: {claim.row.ordering_date} · {claim.row.account_label} · {correctionMoney(claim.row.amount_minor, claim.row.currency)}
            </p>
            <label className="block">
              Claim name
              <input aria-label="Claim name" className="block border bg-background p-1" value={claim.id} onChange={(e) => setClaim({ ...claim, id: e.target.value })} />
            </label>
            <label className="block">
              Amount attributed to the claim
              <input aria-label="Claim amount" className="block border bg-background p-1" value={claim.amount} onChange={(e) => setClaim({ ...claim, amount: e.target.value })} />
            </label>
            <label className="block">
              Why this amount belongs to the claim
              <textarea aria-label="Claim basis" className="block w-full border bg-background p-1" maxLength={4096} value={claim.basis} onChange={(e) => setClaim({ ...claim, basis: e.target.value })} />
            </label>
          </div>
        )}
      </fieldset>
      <fieldset className="space-y-2 rounded border p-3">
        <legend>2. Select the transfers to follow ({pairs.length} selected)</legend>
        <input
          aria-label="Search possible transfers"
          className="block w-full border bg-background p-2"
          value={pairSearch}
          onChange={(e) => {
            setPairSearch(e.target.value)
            setPairOffset(0)
          }}
        />
        <ul className="space-y-1 text-sm">
          {candidates.data?.items
            .filter((p) => p.currency === chosenCurrency)
            .map((p) => {
              const key = `${p.debit_id}:${p.credit_id}`
              const checked = pairs.some((x) => `${x.debit_id}:${x.credit_id}` === key)
              return (
                <li key={key}>
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      aria-label={`Follow transfer on ${p.debit.ordering_date}`}
                      checked={checked}
                      onChange={() => setPairs(checked ? pairs.filter((x) => `${x.debit_id}:${x.credit_id}` !== key) : [...pairs, p])}
                    />
                    {correctionMoney(p.amount_minor, p.currency)} · {p.debit.account_label} ({p.debit.ordering_date}) → {p.credit.account_label} ({p.credit.ordering_date})
                  </label>
                </li>
              )
            })}
        </ul>
        <WholeCasePager label="transfers" offset={pairOffset} size={PAGE} total={candidates.data?.total ?? 0} onOffset={setPairOffset} />
        {pairs.length > 0 && (
          <label className="block text-sm">
            Why these payments are transfers
            <textarea aria-label="Transfer basis" className="block w-full border bg-background p-1" maxLength={4096} value={pairBasis} onChange={(e) => setPairBasis(e.target.value)} />
          </label>
        )}
      </fieldset>
      <fieldset className="space-y-2 rounded border p-3">
        <legend>Record what a withdrawal became ({assetUses.length} recorded, optional)</legend>
        <p className="text-sm">
          An asset interpretation annotates a money-out payment with what it bought. It never changes the cash figures
          and cannot name a payment already selected as a transfer.
        </p>
        <input
          aria-label="Search money-out payments"
          placeholder="Name, date, description or amount"
          className="block w-full border bg-background p-2"
          value={assetSearch}
          onChange={(e) => {
            setAssetSearch(e.target.value)
            setAssetOffset(0)
          }}
        />
        <ul className="space-y-1 text-sm">
          {debits.data?.items
            .filter(
              (row) =>
                row.currency === chosenCurrency &&
                !assetUses.some((use) => use.row.key === row.key) &&
                !pairs.some((p) => p.debit_id === row.key)
            )
            .map((row) => (
              <li key={row.key} className="flex items-center gap-2">
                <Button size="sm" variant="outline" onClick={() => setAssetUses([...assetUses, { row, label: "", basis: "" }])}>
                  Record as asset use
                </Button>
                {row.ordering_date} · {row.account_label} · {correctionMoney(row.amount_minor, row.currency)} · {row.description}
              </li>
            ))}
        </ul>
        {assetSearch.trim() && (
          <WholeCasePager label="payments" offset={assetOffset} size={PAGE} total={debits.data?.total ?? 0} onOffset={setAssetOffset} />
        )}
        {assetUses.map((use, i) => (
          <div key={use.row.key} className="space-y-1 rounded border p-2 text-sm">
            <p>
              {use.row.ordering_date} · {use.row.account_label} · {correctionMoney(use.row.amount_minor, use.row.currency)} ·{" "}
              {use.row.description}
            </p>
            <label className="block">
              What it became
              <input
                aria-label={`Asset label ${i + 1}`}
                className="block w-full border bg-background p-1"
                maxLength={256}
                value={use.label}
                onChange={(e) => setAssetUses(assetUses.map((u, j) => (j === i ? { ...u, label: e.target.value } : u)))}
              />
            </label>
            <label className="block">
              Why
              <textarea
                aria-label={`Asset basis ${i + 1}`}
                className="block w-full border bg-background p-1"
                maxLength={4096}
                value={use.basis}
                onChange={(e) => setAssetUses(assetUses.map((u, j) => (j === i ? { ...u, basis: e.target.value } : u)))}
              />
            </label>
            <Button size="sm" variant="outline" onClick={() => setAssetUses(assetUses.filter((_, j) => j !== i))}>
              Remove asset use {i + 1}
            </Button>
          </div>
        ))}
      </fieldset>
      <fieldset className="space-y-2 rounded border p-3">
        <legend>3. State your assumptions</legend>
        {[...accounts].map(([id, label]) => (
          <label key={id} className="block text-sm">
            Opening balance: {label}
            <input
              aria-label={`Opening balance ${label}`}
              className="block border bg-background p-1"
              value={openings[id] ?? ""}
              onChange={(e) => setOpenings({ ...openings, [id]: e.target.value })}
            />
          </label>
        ))}
        <label className="block text-sm">
          Basis for the opening balances
          <textarea aria-label="Opening basis" className="block w-full border bg-background p-1" maxLength={4096} value={openingBasis} onChange={(e) => setOpeningBasis(e.target.value)} />
        </label>
        <label className="block text-sm">
          Basis for the order of payments (recorded date, then position on the statement)
          <textarea aria-label="Order basis" className="block w-full border bg-background p-1" maxLength={4096} value={orderBasis} onChange={(e) => setOrderBasis(e.target.value)} />
        </label>
        <label className="block text-sm">
          Steps to follow
          <input aria-label="Steps" type="number" min={0} max={25} className="block w-24 border bg-background p-1" value={steps} onChange={(e) => setSteps(Number(e.target.value))} />
        </label>
        {Object.entries(traceMethods).map(([key, method]) => (
          <label key={key} className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              aria-label={method.label}
              checked={methods.includes(key)}
              onChange={() => setMethods(methods.includes(key) ? methods.filter((m) => m !== key) : [...methods, key])}
            />
            {method.label}
          </label>
        ))}
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            aria-label="Allow backward timing"
            checked={allowBackward}
            onChange={() => setAllowBackward(!allowBackward)}
          />
          Allow backward timing: a receiving credit recorded before its debit is attributed from that later debit (an
          explicit assumption)
        </label>
        {allowBackward && (
          <label className="block text-sm">
            Basis for backward timing
            <textarea
              aria-label="Backward basis"
              className="block w-full border bg-background p-1"
              maxLength={4096}
              value={backwardBasis}
              onChange={(e) => setBackwardBasis(e.target.value)}
            />
          </label>
        )}
        <Button disabled={!ready} onClick={() => submit(steps)}>
          Run this trace
        </Button>
      </fieldset>
      {request && !result && <WholeCaseProgress run={trace.run} error={trace.error} noun="trace" onAgain={trace.again} />}
      {result && trace.run && (
        <section aria-label="Trace result" className="space-y-2 rounded border p-3">
          <h3 className="font-semibold">Conditional result: your assumptions, not ledger facts</h3>
          <p>
            {n(result.readings)} payments in {result.accounts.length} accounts: {result.accounts.map((a) => `${a.label ?? a.account_id} (step ${a.steps_from_start})`).join(", ")}.
            {result.same_day_moves > 0 && ` ${result.same_day_moves} same-day receipts were placed straight after their debit; each is named in the report.`}
          </p>
          {result.stop_words && <p role="status">{result.stop_words}</p>}
          {result.backward_timing_used && (
            <p>
              Backward timing was used: selected earlier receiving credits are attributed from later debits, as your
              recorded assumption states.
            </p>
          )}
          {result.continue_with_steps !== null && <Button onClick={() => submit(result.continue_with_steps!)}>Continue one more step</Button>}
          {Object.entries(result.methods).map(([method, outcome]) => (
            <div key={method}>
              <p className="font-medium">{traceMethods[method as keyof typeof traceMethods]?.label ?? method}</p>
              {Object.entries(outcome.claims).map(([name, figures]) => (
                <p key={name} className="text-sm">
                  {name}: {correctionMoney(figures.root_attributed_minor, chosenCurrency)} attributed ·{" "}
                  {correctionMoney(figures.reported_remaining_minor, chosenCurrency)} reported remaining ·{" "}
                  {correctionMoney(figures.withdrawn_without_selected_transfer_minor, chosenCurrency)} left without a selected transfer ·{" "}
                  {correctionMoney(outcome.unidentified_withdrawals_minor, chosenCurrency)} unidentified withdrawals
                </p>
              ))}
              {(outcome.asset_uses?.length ?? 0) > 0 && (
                <div className="text-sm">
                  <p>Asset uses under this method (annotations only; cash figures unchanged):</p>
                  {outcome.asset_uses!.map((use) => (
                    <p key={`${use.transaction_id}:${use.asset_label}`}>
                      {use.asset_label}: {correctionMoney(use.asset_amount_minor, use.currency)} of a{" "}
                      {correctionMoney(use.amount_minor, use.currency)} withdrawal ·{" "}
                      {Object.entries(use.allocated_by_claim)
                        .map(([name, minor]) => `${name} ${correctionMoney(minor, use.currency)}`)
                        .join(" · ") || "no claim share"}{" "}
                      · outside claims {correctionMoney(use.outside_claims_minor, use.currency)}
                    </p>
                  ))}
                </div>
              )}
            </div>
          ))}
          <a className="text-sm underline" href={wholeCaseFileUrl(caseId, trace.run.id, "trace-report.json")} download>
            Download the complete trace report
          </a>
        </section>
      )}
      {(summary.accounts?.length ?? 0) > 0 && (
        <WholeCaseSources
          caseId={caseId}
          accounts={summary.accounts!}
          snapshot={summary.snapshot_sha256}
          currency={chosenCurrency}
          start={start}
          end={end}
          population={population}
          tolerance={tolerance}
          pairs={pairs.map((p) => ({ debit_id: p.debit_id, credit_id: p.credit_id }))}
          pairBasis={pairBasis}
        />
      )}
    </div>
  )
}

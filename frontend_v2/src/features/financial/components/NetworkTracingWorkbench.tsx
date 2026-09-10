import { TraceAssetFields, TraceAssetResultsPanel } from "./TraceAssetFields"
import type { TraceAssetUse } from "../lib/trace-assets"
import { useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { candidateUrl } from "../lib/candidate-contract"
import { correctionMinor, correctionMoney } from "../lib/correction-contract"
import { methods } from "../lib/ledger-trace"
import {
  networkInputs,
  verifyNetworkTrace,
  type NetworkInputs,
} from "../lib/network-trace"
import {
  TraceAttributionFields,
  type DraftAttribution,
} from "./TraceAttributionFields"
import { RequestedCoveragePanel } from "./RequestedCoveragePanel"
import { LedgerSourceDialog } from "./LedgerSourceDialog"
export function NetworkTracingWorkbench({ caseId }: { caseId: string }) {
  const [start, setStart] = useState(""),
    [end, setEnd] = useState(""),
    [population, setPopulation] = useState("verified"),
    [tolerance, setTolerance] = useState("3")
  const load = useMutation({
    retry: false,
    mutationFn: async () => {
      const data = networkInputs.parse(
        await fetchAPI(
          `${candidateUrl("network-trace-inputs", caseId)}&${new URLSearchParams({ start_date: start, end_date: end, population, tolerance_days: tolerance })}`,
          { timeout: 120000 }
        )
      )
      if (
        data.case_id !== caseId ||
        data.start_date !== start ||
        data.end_date !== end ||
        data.population !== population ||
        data.tolerance_days !== Number(tolerance)
      )
        throw Error("Cross-account inputs returned for a different scope.")
      return data
    },
  })
  return (
    <section
      aria-label="Cross-account conditional tracing"
      className="space-y-4 p-4"
    >
      <h2 className="font-semibold">Trace between accounts</h2>
      <p>
        Compare how each selected method carries claim amounts through explicit
        transfer pairs. The calculation keeps each account’s movements and
        original sources.
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          load.mutate()
        }}
        onChange={() => load.reset()}
      >
        <fieldset
          disabled={load.isPending}
          className="flex flex-wrap items-end gap-3"
        >
          <label>
            Trace from date
            <input
              aria-label="Trace from date"
              type="date"
              required
              value={start}
              onChange={(e) => setStart(e.target.value)}
              className="block border bg-background p-2"
            />
          </label>
          <label>
            Trace through date
            <input
              aria-label="Trace through date"
              type="date"
              required
              min={start}
              value={end}
              onChange={(e) => setEnd(e.target.value)}
              className="block border bg-background p-2"
            />
          </label>
          <label>
            Cross-account population
            <select
              aria-label="Cross-account population"
              value={population}
              onChange={(e) => setPopulation(e.target.value)}
              className="block border bg-background p-2"
            >
              <option value="verified">Verified only</option>
              <option value="working">Working readings, including P3</option>
            </select>
          </label>
          <label>
            Transfer date tolerance
            <input
              aria-label="Transfer date tolerance"
              type="number"
              min="0"
              max="7"
              required
              value={tolerance}
              onChange={(e) => setTolerance(e.target.value)}
              className="block w-20 border bg-background p-2"
            />
          </label>
          <Button type="submit">
            {load.isPending ? "Loading…" : "Load cross-account inputs"}
          </Button>
        </fieldset>
      </form>
      {load.isError && <p role="alert">{load.error.message}</p>}
      {load.data && (
        <NetworkCurrency
          key={
            load.data.snapshot_sha256 +
            load.data.population +
            load.data.tolerance_days
          }
          scope={load.data}
        />
      )}
    </section>
  )
}
function NetworkCurrency({ scope }: { scope: NetworkInputs }) {
  const currencies = [...new Set(scope.rows.map((r) => r.currency))],
    [currency, setCurrency] = useState(currencies[0] ?? "")
  if (!currencies.length)
    return (
      <p>
        No current readings in this population and date scope. This does not
        establish that no transfers occurred.
      </p>
    )
  return (
    <>
      <label>
        Cross-account currency
        <select
          aria-label="Cross-account currency"
          className="ml-2 border bg-background p-2"
          value={currency}
          onChange={(e) => setCurrency(e.target.value)}
        >
          {currencies.map((c) => (
            <option key={c}>{c}</option>
          ))}
        </select>
      </label>
      <NetworkForm key={currency} scope={scope} currency={currency} />
    </>
  )
}
function NetworkForm({
  scope,
  currency,
}: {
  scope: NetworkInputs
  currency: string
}) {
  const accounts = scope.accounts.filter((a) => a.currency === currency),
    candidates = scope.candidates.filter((p) => p.currency === currency)
  const [ordered, setOrdered] = useState(() =>
    scope.rows
      .filter((r) => r.currency === currency)
      .sort((a, b) => a.ordering_date.localeCompare(b.ordering_date))
  )
  const [openings, setOpenings] = useState(() =>
      accounts.map((a) => ({
        account_id: a.account_id,
        amount_input: "",
        basis: "",
      }))
    ),
    [attributions, setAttributions] = useState<DraftAttribution[]>([
      { transaction_id: "", claim_id: "", amount_input: "", basis: "" },
    ]),
    [chosen, setChosen] = useState<number[]>([]),
    [selectedMethods, setSelectedMethods] = useState<string[]>([]),
    [basis, setBasis] = useState(""),
    [assetUses, setAssetUses] = useState<TraceAssetUse[]>([]),
    [allowBackward, setAllowBackward] = useState(false),
    [backwardBasis, setBackwardBasis] = useState(""),
    [orderBasis, setOrderBasis] = useState(""),
    [pairPage, setPairPage] = useState(0),
    [source, setSource] = useState<string | null>(null)
  const selectedPairs = chosen.map((i) => candidates[i]),
    used = new Set(selectedPairs.flatMap((p) => [p.debit_id, p.credit_id])),
    receiving = new Set(selectedPairs.map((p) => p.credit_id))
  const accountLabel = (id: string) =>
    accounts.find((a) => a.account_id === id)?.label ?? id
  const calculate = useMutation({
    retry: false,
    mutationFn: async () => {
      const request = {
        expected_snapshot_sha256: scope.snapshot_sha256,
        population: scope.population,
        tolerance_days: scope.tolerance_days,
        start_date: scope.start_date,
        end_date: scope.end_date,
        currency,
        pairs: selectedPairs.map((p) => ({
          debit_id: p.debit_id,
          credit_id: p.credit_id,
        })),
        basis,
        order_basis: orderBasis,
        asset_uses: assetUses.map(({ asset_amount_input, resale, ...use }) => ({
          ...use,
          ...(resale
            ? {
                resale: {
                  transaction_id: resale.transaction_id,
                  basis: resale.basis,
                  allocation_basis: resale.allocation_basis,
                  proceeds_minor: correctionMinor(
                    resale.proceeds_input,
                    currency
                  ),
                },
              }
            : {}),
          ...(asset_amount_input === undefined
            ? {}
            : {
                asset_amount_minor: correctionMinor(
                  asset_amount_input,
                  currency
                ),
                allocation_basis: "proportional_share",
              }),
        })),
        allow_backward: allowBackward,
        backward_basis: allowBackward ? backwardBasis : "",
        ordered_transaction_ids: ordered.map((r) => r.key),
        doctrines: selectedMethods,
        openings: openings.map(({ amount_input, ...o }) => ({
          ...o,
          amount_minor: correctionMinor(amount_input, currency),
        })),
        attributions: attributions.map(({ amount_input, ...a }) => ({
          ...a,
          amount_minor: correctionMinor(amount_input, currency),
        })),
      }
      if (
        request.openings.some((o) => o.amount_minor === null) ||
        request.attributions.some(
          (a) => a.amount_minor === null || a.amount_minor === "0"
        )
      )
        throw Error(
          `Enter exact ${currency} amounts; root attributions must be positive.`
        )
      return verifyNetworkTrace(
        await fetchAPI(candidateUrl("network-trace", scope.case_id), {
          method: "POST",
          body: request,
          timeout: 120000,
        }),
        scope,
        request
      )
    },
  })
  const reset = () => calculate.reset()
  const download = () => {
    if (!calculate.data) return
    const url = URL.createObjectURL(
        new Blob([calculate.data.envelope.scenario_json], {
          type: "application/json",
        })
      ),
      a = document.createElement("a")
    a.href = url
    a.download = "loupe-cross-account-trace.json"
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  if (
    accounts.length < 2 ||
    accounts.length > 10 ||
    ordered.length > scope.network_row_limit
  )
    return (
      <p>
        Choose a date scope with 2–10 accounts and at most{" "}
        {scope.network_row_limit} current readings in one currency. No partial
        trace is calculated.
      </p>
    )
  return (
    <div className="space-y-4">
      <p>
        {ordered.length} {scope.population} postings across {accounts.length}{" "}
        accounts. {scope.excluded_rows} readings excluded from this population.
      </p>
      <p>{scope.network_limitation}</p>
      {scope.date_unavailable_ids.some((id) =>
        ordered.some((r) => r.key === id)
      ) && (
        <p role="status">
          Some readings use statement-end dates for ordering because their
          transaction dates are unknown. They remain in the account calculation,
          but cannot supply transfer timing. Inspect their sources and explain
          the assumed order.
        </p>
      )}
      <form
        onSubmit={(e) => {
          e.preventDefault()
          calculate.mutate()
        }}
        onChange={reset}
      >
        <fieldset disabled={calculate.isPending} className="space-y-4">
          <legend className="font-semibold">Cross-account assumptions</legend>
          <h3 className="font-semibold">Opening funds for each account</h3>
          {openings.map((o, i) => (
            <div
              key={o.account_id}
              className="grid gap-2 rounded border p-3 sm:grid-cols-2"
            >
              <p className="sm:col-span-2">{accountLabel(o.account_id)}</p>
              <div className="sm:col-span-2">
                <RequestedCoveragePanel
                  caseId={scope.case_id}
                  params={{
                    accountId: o.account_id,
                    startDate: scope.start_date ?? undefined,
                    endDate: scope.end_date ?? undefined,
                  }}
                />
              </div>
              <label>
                Opening amount ({currency})
                <input
                  aria-label={`Opening amount account ${i + 1}`}
                  required
                  maxLength={32}
                  inputMode="decimal"
                  className="block border bg-background p-2"
                  value={o.amount_input}
                  onChange={(e) =>
                    setOpenings((v) =>
                      v.map((a, n) =>
                        n === i ? { ...a, amount_input: e.target.value } : a
                      )
                    )
                  }
                />
              </label>
              <label>
                Opening basis
                <textarea
                  aria-label={`Opening basis account ${i + 1}`}
                  required
                  maxLength={4096}
                  className="block w-full border bg-background p-2"
                  value={o.basis}
                  onChange={(e) =>
                    setOpenings((v) =>
                      v.map((a, n) =>
                        n === i ? { ...a, basis: e.target.value } : a
                      )
                    )
                  }
                />
              </label>
            </div>
          ))}
          <h3 className="font-semibold">Choose transfer assumptions</h3>
          <p>
            Equal amount and compatible timing suggest a match; they do not
            prove it. A posting can be used in one pair. Receiving credits are
            not separate root attributions.
          </p>
          {!candidates.length && (
            <p>
              No proposed transfer pairs in this scope. A cross-account scenario
              requires a pair.
            </p>
          )}
          {candidates
            .slice(pairPage * 25, pairPage * 25 + 25)
            .map((p, index) => {
              const i = pairPage * 25 + index,
                d = ordered.find((r) => r.key === p.debit_id)!,
                c = ordered.find((r) => r.key === p.credit_id)!
              return (
                <div key={i} className="rounded border p-3">
                  <label className="flex gap-2">
                    <input
                      aria-label={`Trace transfer pair ${i + 1}`}
                      type="checkbox"
                      checked={chosen.includes(i)}
                      disabled={
                        !chosen.includes(i) &&
                        (used.has(p.debit_id) || used.has(p.credit_id))
                      }
                      onChange={(e) => {
                        reset()
                        setChosen((v) =>
                          e.target.checked
                            ? [...v, i]
                            : v.filter((n) => n !== i)
                        )
                      }}
                    />
                    <span>
                      {accountLabel(d.account_id)} →{" "}
                      {accountLabel(c.account_id)} ·{" "}
                      {correctionMoney(p.amount_minor, currency)} ·{" "}
                      {p.outcome === "ambiguous"
                        ? "Multiple possible partners"
                        : "One proposed partner"}{" "}
                      · {d.ordering_date} / {c.ordering_date}
                    </span>
                  </label>
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => setSource(p.debit_id)}
                  >
                    Inspect sending posting {i + 1}
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => setSource(p.credit_id)}
                  >
                    Inspect receiving posting {i + 1}
                  </Button>
                </div>
              )
            })}
          {candidates.length > 25 && (
            <div className="flex gap-2">
              <Button
                type="button"
                disabled={!pairPage}
                onClick={() => setPairPage(pairPage - 1)}
              >
                Previous trace pairs
              </Button>
              <Button
                type="button"
                disabled={(pairPage + 1) * 25 >= candidates.length}
                onClick={() => setPairPage(pairPage + 1)}
              >
                Next trace pairs
              </Button>
            </div>
          )}
          <label className="block">
            Basis for selected transfers
            <textarea
              aria-label="Basis for selected transfers"
              required
              maxLength={4096}
              className="block w-full border bg-background p-2"
              value={basis}
              onChange={(e) => setBasis(e.target.value)}
            />
          </label>
          <TraceAttributionFields
            currency={currency}
            credits={ordered
              .filter((r) => r.direction === "credit" && !receiving.has(r.key))
              .map((r) => ({
                id: r.key,
                label: `${accountLabel(r.account_id)} · ${r.ordering_date} · ${correctionMoney(r.amount_minor, currency)} · ${r.key}`,
              }))}
            value={attributions}
            onChange={(v) => {
              reset()
              setAttributions(v)
            }}
          />
          <fieldset className="space-y-2 rounded border p-3">
            <legend>Optional backward timing</legend>
            <label className="block">
              <input
                aria-label="Allow backward transfer timing"
                type="checkbox"
                checked={allowBackward}
                onChange={(e) => setAllowBackward(e.target.checked)}
              />{" "}
              Allow a receiving credit before its selected debit
            </label>
            <p>
              Off by default. This assumes an earlier receiving entry is linked
              to a later payment; it does not establish causation or legal
              applicability. Circular account dependencies are refused. Recorded
              dates stay unchanged.
            </p>
            {allowBackward && (
              <label className="block">
                Basis for backward timing
                <textarea
                  aria-label="Basis for backward timing"
                  required
                  maxLength={4096}
                  className="block w-full border bg-background p-2"
                  value={backwardBasis}
                  onChange={(e) => setBackwardBasis(e.target.value)}
                />
              </label>
            )}
          </fieldset>
          <TraceAssetFields
            value={assetUses}
            onChange={(v) => {
              setAssetUses(v)
              reset()
            }}
            receipts={ordered
              .filter(
                (r) =>
                  r.direction === "credit" &&
                  BigInt(r.amount_minor) > 0n &&
                  !used.has(r.key)
              )
              .map((r) => ({
                id: r.key,
                label: `${accountLabel(r.account_id)} · ${r.ordering_date} · ${correctionMoney(r.amount_minor, currency)}`,
              }))}
            withdrawals={ordered
              .filter(
                (r) =>
                  r.direction === "debit" &&
                  BigInt(r.amount_minor) > 0n &&
                  !used.has(r.key)
              )
              .map((r) => ({
                id: r.key,
                label: `${accountLabel(r.account_id)} · ${r.ordering_date} · ${correctionMoney(r.amount_minor, currency)}`,
              }))}
          />
          <h3 className="font-semibold">Review the movement order</h3>
          <p>
            All current readings in this currency are included. Same-day order
            is an assumption. Forward mode requires each receiving credit after
            its selected debit; backward timing requires the explicit option and
            basis above.
          </p>
          <ol className="max-h-96 overflow-auto rounded border p-3">
            {ordered.map((r, i) => (
              <li key={r.key} className="border-b py-2">
                {i + 1}. {r.ordering_date} · {accountLabel(r.account_id)} ·{" "}
                {r.direction} {correctionMoney(r.amount_minor, currency)} ·{" "}
                {r.description}
                {scope.date_unavailable_ids.includes(r.key) && (
                  <span>
                    {" "}
                    · Transaction date unknown; statement-end ordering only
                  </span>
                )}
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => setSource(r.key)}
                >
                  Open network source {i + 1}
                </Button>
                {i > 0 && ordered[i - 1].ordering_date === r.ordering_date && (
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => {
                      reset()
                      setOrdered((v) => {
                        const next = [...v]
                        ;[next[i - 1], next[i]] = [next[i], next[i - 1]]
                        return next
                      })
                    }}
                  >
                    Move network reading {i + 1} earlier
                  </Button>
                )}
              </li>
            ))}
          </ol>
          <label className="block">
            Basis for cross-account order
            <textarea
              aria-label="Basis for cross-account order"
              required
              maxLength={4096}
              className="block w-full border bg-background p-2"
              value={orderBasis}
              onChange={(e) => setOrderBasis(e.target.value)}
            />
          </label>
          <p>Select the calculation methods to compare.</p>
          {methods.map((m) => (
            <label key={m} className="block">
              <input
                type="checkbox"
                checked={selectedMethods.includes(m)}
                onChange={(e) =>
                  setSelectedMethods((v) =>
                    e.target.checked ? [...v, m] : v.filter((x) => x !== m)
                  )
                }
              />
              {m.replaceAll("_", " ")}
            </label>
          ))}
          <Button
            type="submit"
            disabled={
              !chosen.length || !selectedMethods.length || calculate.isPending
            }
          >
            {calculate.isPending
              ? "Calculating…"
              : "Calculate cross-account scenario"}
          </Button>
        </fieldset>
      </form>
      {calculate.isError && <p role="alert">{calculate.error.message}</p>}
      {calculate.data && (
        <section
          aria-label="Cross-account tracing results"
          className="space-y-4"
        >
          <h3 className="font-semibold">Conditional results by method</h3>
          <div className="overflow-x-auto">
            <table
              className="w-full text-left text-sm"
              aria-label="Cross-account method comparison"
            >
              <thead>
                <tr>
                  {[
                    "Method",
                    "Claim",
                    "Root amount",
                    "Reported remaining",
                    "Withdrawn without selected transfer",
                    "Unidentified withdrawals (all claims)",
                  ].map((label) => (
                    <th className="border-b p-2" key={label} scope="col">
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {Object.entries(calculate.data.value.results).flatMap(
                  ([method, result]) =>
                    Object.entries(result.claims).map(([claim, c]) => (
                      <tr key={method + ":" + claim}>
                        <th className="border-b p-2" scope="row">
                          {method.replaceAll("_", " ")}
                        </th>
                        <td className="border-b p-2">{claim}</td>
                        {[
                          c.root_attributed_minor,
                          c.reported_remaining_minor,
                          c.withdrawn_without_selected_transfer_minor,
                          result.unidentified_withdrawals_minor,
                        ].map((amount, i) => (
                          <td key={i} className="border-b p-2 tabular-nums">
                            {correctionMoney(amount, currency)}
                          </td>
                        ))}
                      </tr>
                    ))
                )}
              </tbody>
            </table>
          </div>
          {calculate.data.value.backward_timing_used && (
            <p className="font-semibold">
              Backward timing used — allocations to earlier receiving entries
              are conditional on your stated basis.
            </p>
          )}
          {calculate.data.value.limitations.map((note) => (
            <p key={note}>{note}</p>
          ))}
          {Object.entries(calculate.data.value.results).map(
            ([method, result]) => (
              <article key={method} className="space-y-3 rounded border p-4">
                <h4 className="font-semibold">{method.replaceAll("_", " ")}</h4>
                {Object.entries(result.claims).map(([claim, c]) => (
                  <p key={claim}>
                    {claim}: root{" "}
                    {correctionMoney(c.root_attributed_minor, currency)} ·
                    reported remaining{" "}
                    {correctionMoney(c.reported_remaining_minor, currency)} ·
                    withdrawn without a selected transfer{" "}
                    {correctionMoney(
                      c.withdrawn_without_selected_transfer_minor,
                      currency
                    )}
                  </p>
                ))}
                <p>
                  Unidentified withdrawals:{" "}
                  {correctionMoney(
                    result.unidentified_withdrawals_minor,
                    currency
                  )}
                  . Read remaining figures alongside this uncertainty.
                </p>
                <TraceAssetResultsPanel
                  items={result.asset_uses}
                  onSource={setSource}
                />
                {result.hops.map((h, i) => (
                  <div key={h.debit_id} className="rounded border p-2">
                    <p>
                      Hop {i + 1}: {accountLabel(h.from_account)} →{" "}
                      {accountLabel(h.to_account)}
                    </p>
                    {h.backward_timing && (
                      <p>
                        Earlier receiving entry — explicit backward timing
                        assumption.
                      </p>
                    )}
                    {Object.entries(h.propagated_by_claim).map(
                      ([claim, amount]) => (
                        <p key={claim}>
                          {claim}: {correctionMoney(amount, currency)} carried
                          onward
                        </p>
                      )
                    )}
                    <p>
                      Outside attributed claim shares:{" "}
                      {correctionMoney(
                        h.unattributed_or_unidentified_minor,
                        currency
                      )}
                    </p>
                    <Button
                      variant="outline"
                      onClick={() => setSource(h.debit_id)}
                    >
                      Open hop {i + 1} debit
                    </Button>
                    <Button
                      variant="outline"
                      onClick={() => setSource(h.credit_id)}
                    >
                      Open hop {i + 1} credit
                    </Button>
                  </div>
                ))}
                <details>
                  <summary>Per-account calculation details</summary>
                  {Object.entries(result.accounts).map(([id, a]) => (
                    <div key={id}>
                      <p>
                        {accountLabel(id)} · closing{" "}
                        {correctionMoney(
                          a.closing_balance.minor_units,
                          currency
                        )}
                      </p>
                      {Object.entries(a.outcomes).map(([claim, o]) => (
                        <p key={claim}>
                          {claim}:{" "}
                          {correctionMoney(o.surviving.minor_units, currency)}{" "}
                          remaining under this method
                        </p>
                      ))}
                      {a.notes.map((n) => (
                        <p key={n}>{n}</p>
                      ))}
                    </div>
                  ))}
                </details>
              </article>
            )
          )}
          <Button onClick={download}>Download cross-account scenario</Button>
        </section>
      )}
      {source && (
        <LedgerSourceDialog
          caseId={scope.case_id}
          transactionId={source}
          onClose={() => setSource(null)}
        />
      )}
    </div>
  )
}

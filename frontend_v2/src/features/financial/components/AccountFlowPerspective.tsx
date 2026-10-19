import { ConditionalTransferGraph } from "./ConditionalTransferGraph"
import { AccountPartyDirectory } from "./AccountPartyDirectory"
import { useAccountPerspective } from "../stores/account-perspective"
import { useState } from "react"
import { Button } from "@/components/ui/button"
import type { TransferInputs } from "../lib/ledger-transfers"
import { accountPerspective } from "../lib/flow-perspective"
import { correctionMoney } from "../lib/correction-contract"
import { LedgerFlowChart } from "./LedgerFlowChart"
export function AccountFlowPerspective({
  scope,
  scenarioJson,
  onSource,
}: {
  scope: TransferInputs
  scenarioJson?: string
  onSource: (id: string) => void
}) {
  const [showParties, setShowParties] = useState(false)
  const [perspective, setPerspective] = useAccountPerspective(scope.case_id)
  const partyCapture = perspective.partyCapture
  const accounts = [
    ...new Map(
      scope.rows.map((r) => [
        r.account_id,
        {
          id: r.account_id,
          label: r.account_label ?? "Account " + r.account_id.slice(0, 8),
        },
      ])
    ).values(),
  ]
  const selected = perspective.accountIds.filter((id) =>
    accounts.some((account) => account.id === id)
  )
  const outsideCount = perspective.accountIds.length - selected.length
  // The parent only supplies bytes already checked by verifyTransferScenario.
  const scenario = scenarioJson ? JSON.parse(scenarioJson) : null
  const pairs: { debit_id: string; credit_id: string }[] =
    scenario?.inputs.pairs ?? []
  const result = accountPerspective(scope, selected, pairs)
  const download = () => {
    const value = {
      schema: "loupe.financial.account_perspective/1",
      case_id: scope.case_id,
      selected_account_ids: selected,
      account_party_decisions: partyCapture,
      scope,
      result,
      transfer_scenario: scenario,
      limitation:
        "Conditional account perspective. Only explicitly calculated transfer pairs count once. Unpaired postings may include unidentified internal transfers. Source labels do not establish party identity. This selection does not change the ledger.",
    }
    const url = URL.createObjectURL(
        new Blob([JSON.stringify(value, null, 2)], { type: "application/json" })
      ),
      a = document.createElement("a")
    a.href = url
    a.download = "loupe-account-flow-perspective.json"
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  return (
    <section
      aria-label="Account flow perspective"
      className="space-y-3 rounded border p-4"
    >
      <h3 className="font-semibold">
        Money entering and leaving an account group
      </h3>
      <p>
        Select the accounts to examine together. Paired movements within the
        group count once as internal and stay out of the incoming/outgoing
        comparison. Unpaired postings may still include internal movements that
        have not been identified.
      </p>
      <p>
        {pairs.length} calculated transfer assumptions applied.{" "}
        {scenario
          ? "Their saved reasoning and source snapshot are included in the perspective download."
          : "Calculate the selected transfer scenario above to apply pairings; selecting a checkbox alone does not apply it."}
      </p>
      {scenario && (
        <ConditionalTransferGraph
          key={scenarioJson}
          scope={scope}
          pairs={pairs}
          onSource={onSource}
        />
      )}
      <Button onClick={() => setShowParties((v) => !v)}>
        {showParties
          ? "Hide account party links"
          : "Review account-to-party links"}
      </Button>
      {showParties && (
        <AccountPartyDirectory
          caseId={scope.case_id}
          onChoose={(ids, capture) => {
            setPerspective({ accountIds: ids, partyCapture: capture })
          }}
        />
      )}
      {partyCapture && (
        <p>
          Using saved party links from this capture. Only linked accounts
          present in the loaded transaction scope are included; the link history
          is included in the download.
        </p>
      )}
      {outsideCount > 0 && (
        <p role="status">
          {outsideCount} selected accounts have no transactions in this date
          range. They remain selected for other dates and do not contribute to
          these totals.
        </p>
      )}
      {perspective.accountIds.length > 0 && (
        <Button
          variant="outline"
          onClick={() => setPerspective({ accountIds: [], partyCapture: null })}
        >
          Clear account group
        </Button>
      )}
      <fieldset className="grid gap-2 sm:grid-cols-2">
        <legend>Accounts in this perspective</legend>
        {accounts.map((a) => (
          <label key={a.id}>
            <input
              type="checkbox"
              aria-label={`Include account ${a.label}`}
              checked={selected.includes(a.id)}
              onChange={(e) => {
                setPerspective({
                  partyCapture: null,
                  accountIds: e.target.checked
                    ? [...perspective.accountIds, a.id]
                    : perspective.accountIds.filter((id) => id !== a.id),
                })
              }}
            />{" "}
            {a.label}
          </label>
        ))}
      </fieldset>
      {!selected.length ? (
        <p>Choose at least one account to calculate this perspective.</p>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table
              className="w-full text-left"
              aria-label="Account group movement totals"
            >
              <thead>
                <tr>
                  {[
                    "Currency",
                    "Incoming",
                    "Outgoing",
                    "Net",
                    "Internal (once)",
                    "Internal movements",
                  ].map((t) => (
                    <th scope="col" className="border-b p-2" key={t}>
                      {t}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.totals.map((t) => (
                  <tr key={t.currency}>
                    <th scope="row" className="border-b p-2">
                      {t.currency}
                    </th>
                    {[
                      t.incoming_minor,
                      t.outgoing_minor,
                      t.net_minor,
                      t.internal_minor,
                    ].map((amount, i) => (
                      <td className="border-b p-2 tabular-nums" key={i}>
                        {correctionMoney(amount, t.currency)}
                      </td>
                    ))}
                    <td className="border-b p-2">{t.internal_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <LedgerFlowChart
            groups={result.groups}
            title="Account group external flow"
            onSource={onSource}
            explanation="Outgoing movements extend left and incoming movements right. Selected internal pairs are excluded from this chart. Unpaired source-label groups remain local to their account; equal labels do not establish the same party. Groups are ordered by net within each currency."
          />
          <details>
            <summary>
              Internal movements and their sources (
              {result.movements.filter((m) => m.kind === "internal").length})
            </summary>
            {result.movements
              .filter((m) => m.kind === "internal")
              .map((m, i) => (
                <div
                  key={m.transaction_ids.join(":")}
                  className="rounded border p-2"
                >
                  <p>
                    Internal {i + 1}:{" "}
                    {correctionMoney(m.amount_minor, m.currency)} counted once
                  </p>
                  {m.transaction_ids.map((id, n) => (
                    <Button
                      key={id}
                      variant="outline"
                      onClick={() => onSource(id)}
                    >
                      Open internal {i + 1} {n === 0 ? "debit" : "credit"}
                    </Button>
                  ))}
                </div>
              ))}
          </details>
          <Button onClick={download}>
            Download account perspective and assumptions
          </Button>
        </>
      )}
    </section>
  )
}
